import asyncio
import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import (
    AnalyticsExportJobDB,
    AnalyticsSnapshotScheduleDB,
    ConversationDB,
    MessageDB,
    SessionLocal,
    get_db,
)
from app.core.logging import logger
from app.core.security import get_current_user_id

router = APIRouter()

METRIC_DICTIONARY = [
    {
        "metric": "team_frt_p50_ms",
        "description": "Median first response time per agent in milliseconds.",
        "formula": "median(agent_or_bot_message_ts - first_user_message_ts)",
        "version": "v1",
        "last_updated": "2026-02-25",
    },
    {
        "metric": "team_frt_p95_ms",
        "description": "95th percentile first response time per agent in milliseconds.",
        "formula": "p95(agent_or_bot_message_ts - first_user_message_ts)",
        "version": "v1",
        "last_updated": "2026-02-25",
    },
    {
        "metric": "transfer_anomaly_score",
        "description": "Ratio current transfer-rate / baseline transfer-rate.",
        "formula": "(transfers_current/current_total) / (transfers_baseline/baseline_total)",
        "version": "v1",
        "last_updated": "2026-02-25",
    },
]


class AnalyticsScheduleCreate(BaseModel):
    name: str
    frequency: str = Field(pattern="^(daily|weekly)$")
    timezone: str = "UTC"
    report_type: str = "overview"
    recipient_email: str
    is_active: bool = True


class AnalyticsScheduleUpdate(BaseModel):
    name: Optional[str] = None
    frequency: Optional[str] = Field(default=None, pattern="^(daily|weekly)$")
    timezone: Optional[str] = None
    report_type: Optional[str] = None
    recipient_email: Optional[str] = None
    is_active: Optional[bool] = None


class ExportJobCreate(BaseModel):
    report_type: str = "overview"
    filters: Dict[str, Any] = {}


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _scoped_conversations(
    db: Session,
    tenant_id: str,
    bot_id: Optional[int] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
):
    query = db.query(ConversationDB).filter(ConversationDB.tenant_id == tenant_id)
    if bot_id:
        query = query.filter(ConversationDB.bot_id == bot_id)
    if start:
        query = query.filter(ConversationDB.created_at >= start)
    if end:
        query = query.filter(ConversationDB.created_at <= end)
    return query


def _first_response_deltas(db: Session, conv_ids: List[int]) -> Dict[str, List[float]]:
    if not conv_ids:
        return {}
    messages = (
        db.query(MessageDB)
        .filter(MessageDB.conversation_id.in_(conv_ids))
        .order_by(MessageDB.conversation_id.asc(), MessageDB.created_at.asc())
        .all()
    )
    grouped: Dict[int, List[MessageDB]] = defaultdict(list)
    for msg in messages:
        grouped[msg.conversation_id].append(msg)

    by_agent: Dict[str, List[float]] = defaultdict(list)
    for conv_msgs in grouped.values():
        first_user = next((m for m in conv_msgs if m.sender == "user"), None)
        first_reply = next((m for m in conv_msgs if m.sender in {"agent", "bot"}), None)
        if not first_user or not first_reply:
            continue
        delta_ms = (first_reply.created_at - first_user.created_at).total_seconds() * 1000
        if delta_ms < 0:
            continue
        agent_key = first_reply.agent_id or ("agent:unknown" if first_reply.sender == "agent" else "bot:auto")
        by_agent[agent_key].append(delta_ms)
    return by_agent


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return float(ordered[idx])


@router.get("/team/performance")
async def get_team_performance(
    bot_id: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    convs = _scoped_conversations(db, tenant_id, bot_id=bot_id, start=start_dt, end=end_dt).all()
    conv_ids = [c.id for c in convs]
    deltas = _first_response_deltas(db, conv_ids)

    rows = []
    for agent_id, vals in deltas.items():
        rows.append(
            {
                "agent_id": agent_id,
                "handled_sessions": len(vals),
                "frt_p50_ms": round(_percentile(vals, 50), 2),
                "frt_p95_ms": round(_percentile(vals, 95), 2),
            }
        )
    rows.sort(key=lambda r: r["handled_sessions"], reverse=True)
    return {"items": rows, "total_conversations": len(convs)}


@router.get("/team/workload")
async def get_team_workload(
    bot_id: Optional[int] = None,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    convs = _scoped_conversations(db, tenant_id, bot_id=bot_id).all()
    open_by_agent: Dict[str, int] = defaultdict(int)
    handled_by_agent: Dict[str, int] = defaultdict(int)

    conv_ids = [c.id for c in convs]
    msgs = (
        db.query(MessageDB)
        .filter(MessageDB.conversation_id.in_(conv_ids), MessageDB.sender == "agent")
        .order_by(MessageDB.created_at.asc())
        .all()
    ) if conv_ids else []
    for msg in msgs:
        key = msg.agent_id or "agent:unknown"
        handled_by_agent[key] += 1

    for conv in convs:
        if conv.status in {"open", "pending"}:
            latest_agent = (
                db.query(MessageDB)
                .filter(MessageDB.conversation_id == conv.id, MessageDB.sender == "agent")
                .order_by(MessageDB.created_at.desc())
                .first()
            )
            key = (latest_agent.agent_id if latest_agent else "agent:unassigned") or "agent:unassigned"
            open_by_agent[key] += 1

    agents = sorted(set(list(open_by_agent.keys()) + list(handled_by_agent.keys())))
    return {
        "items": [
            {
                "agent_id": a,
                "handled_messages": handled_by_agent.get(a, 0),
                "open_queue_owned": open_by_agent.get(a, 0),
            }
            for a in agents
        ]
    }


@router.get("/team/coverage")
async def get_team_coverage(
    bot_id: Optional[int] = None,
    days: int = Query(default=7, ge=1, le=30),
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start = now - timedelta(days=days)
    convs = _scoped_conversations(db, tenant_id, bot_id=bot_id, start=start).all()
    conv_ids = [c.id for c in convs]
    msgs = (
        db.query(MessageDB)
        .filter(MessageDB.conversation_id.in_(conv_ids))
        .all()
    ) if conv_ids else []
    by_hour = {h: {"demand": 0, "coverage": 0} for h in range(24)}
    for msg in msgs:
        hr = msg.created_at.hour
        if msg.sender == "user":
            by_hour[hr]["demand"] += 1
        if msg.sender in {"agent", "bot"}:
            by_hour[hr]["coverage"] += 1
    rows = []
    for hr in range(24):
        demand = by_hour[hr]["demand"]
        coverage = by_hour[hr]["coverage"]
        gap = max(0, demand - coverage)
        rows.append({"hour": hr, "demand": demand, "coverage": coverage, "gap": gap})
    return {"items": rows}


@router.get("/team/csat-segmentation")
async def get_team_csat_segmentation(
    bot_id: Optional[int] = None,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    convs = _scoped_conversations(db, tenant_id, bot_id=bot_id).all()
    total = len(convs)
    automated = sum(1 for c in convs if c.status == "resolved" and not c.agent_requested)
    assisted = sum(1 for c in convs if c.status == "pending" and c.agent_requested)
    manual = sum(1 for c in convs if c.agent_requested)
    # Proxy scores from lifecycle mix.
    def _score(count: int, base: float) -> float:
        if total == 0:
            return 0.0
        ratio = count / total
        return round(max(0.0, min(5.0, base + ratio * 0.8)), 1)

    return {
        "automated": {"count": automated, "csat": _score(automated, 3.6)},
        "assisted": {"count": assisted, "csat": _score(assisted, 3.4)},
        "manual": {"count": manual, "csat": _score(manual, 3.2)},
    }


@router.get("/quality/insights")
async def get_quality_insights(
    bot_id: Optional[int] = None,
    limit: int = Query(default=10, ge=1, le=50),
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    convs = _scoped_conversations(db, tenant_id, bot_id=bot_id).all()
    unresolved = [c for c in convs if c.status in {"new", "open", "pending"}]
    weak_markers = ["temporarily at capacity", "not found", "could not", "cannot", "not available"]
    clusters: Dict[str, Dict[str, Any]] = {}
    failed_answers = []

    for conv in unresolved:
        msgs = (
            db.query(MessageDB)
            .filter(MessageDB.conversation_id == conv.id)
            .order_by(MessageDB.created_at.asc())
            .all()
        )
        user_msgs = [m for m in msgs if m.sender == "user"]
        bot_msgs = [m for m in msgs if m.sender == "bot"]
        if user_msgs:
            key = (user_msgs[-1].text or "").strip().lower()[:100]
            if key:
                row = clusters.setdefault(
                    key,
                    {"intent": user_msgs[-1].text[:180], "count": 0, "sample_conversation_id": conv.id},
                )
                row["count"] += 1
        for bm in bot_msgs:
            low = (bm.text or "").lower()
            if any(m in low for m in weak_markers):
                failed_answers.append(
                    {
                        "conversation_id": conv.id,
                        "message_id": bm.id,
                        "reason": "fallback_or_low_confidence_pattern",
                        "snippet": (bm.text or "")[:200],
                    }
                )

    unresolved_clusters = sorted(clusters.values(), key=lambda x: x["count"], reverse=True)[:limit]
    coaching = []
    for cluster in unresolved_clusters[: min(5, len(unresolved_clusters))]:
        coaching.append(
            {
                "issue_type": "missing_knowledge_or_workflow",
                "sample_conversation_id": cluster["sample_conversation_id"],
                "suggestion": f"Add canonical answer/flow for: {cluster['intent']}",
                "expected_impact": "Reduce unresolved and transfer volume",
            }
        )
    return {
        "unresolved_clusters": unresolved_clusters,
        "failed_answers": failed_answers[:limit],
        "coaching_suggestions": coaching,
    }


@router.get("/quality/transfer-anomaly")
async def get_transfer_anomaly(
    bot_id: Optional[int] = None,
    current_days: int = Query(default=7, ge=1, le=30),
    baseline_days: int = Query(default=28, ge=7, le=180),
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    current_start = now - timedelta(days=current_days)
    baseline_start = now - timedelta(days=baseline_days)

    current = _scoped_conversations(db, tenant_id, bot_id=bot_id, start=current_start, end=now).all()
    baseline = _scoped_conversations(db, tenant_id, bot_id=bot_id, start=baseline_start, end=current_start).all()

    def _rate(rows: List[ConversationDB]) -> float:
        if not rows:
            return 0.0
        return sum(1 for c in rows if c.agent_requested) / len(rows)

    current_rate = _rate(current)
    baseline_rate = _rate(baseline)
    anomaly_score = (current_rate / baseline_rate) if baseline_rate > 0 else (2.0 if current_rate > 0 else 1.0)
    return {
        "current_transfer_rate": round(current_rate * 100, 2),
        "baseline_transfer_rate": round(baseline_rate * 100, 2),
        "anomaly_score": round(anomaly_score, 3),
        "is_anomaly": anomaly_score >= 1.5 and len(current) >= 5,
    }


@router.get("/v1/metric-dictionary")
async def get_metric_dictionary(tenant_id: str = Depends(get_current_user_id)):
    return {"schema_version": "v1", "tenant_id": tenant_id, "metrics": METRIC_DICTIONARY}


@router.get("/v1/report")
async def get_report_v1(
    report_type: str = Query(default="overview"),
    bot_id: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    convs = _scoped_conversations(db, tenant_id, bot_id=bot_id, start=start_dt, end=end_dt).all()

    items = []
    if report_type == "overview":
        for c in convs:
            items.append(
                {
                    "conversation_id": c.id,
                    "bot_id": c.bot_id,
                    "status": c.status,
                    "agent_requested": bool(c.agent_requested),
                    "created_at": c.created_at.isoformat(),
                }
            )
    elif report_type == "transfers":
        for c in convs:
            if c.agent_requested:
                items.append(
                    {
                        "conversation_id": c.id,
                        "bot_id": c.bot_id,
                        "status": c.status,
                        "created_at": c.created_at.isoformat(),
                    }
                )
    else:
        raise HTTPException(status_code=400, detail="Unsupported report_type")

    total = len(items)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_items = items[start_idx:end_idx]
    return {
        "schema_version": "v1",
        "report_type": report_type,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
        "items": page_items,
    }


@router.post("/reports/schedules")
async def create_schedule(
    payload: AnalyticsScheduleCreate,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    row = AnalyticsSnapshotScheduleDB(tenant_id=tenant_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "status": "created"}


@router.get("/reports/schedules")
async def list_schedules(
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AnalyticsSnapshotScheduleDB)
        .filter(AnalyticsSnapshotScheduleDB.tenant_id == tenant_id)
        .order_by(AnalyticsSnapshotScheduleDB.created_at.desc())
        .all()
    )
    return rows


@router.put("/reports/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    payload: AnalyticsScheduleUpdate,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    row = (
        db.query(AnalyticsSnapshotScheduleDB)
        .filter(AnalyticsSnapshotScheduleDB.id == schedule_id, AnalyticsSnapshotScheduleDB.tenant_id == tenant_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    return {"ok": True}


async def _generate_export_artifact(tenant_id: str, job_id: int):
    db = SessionLocal()
    try:
        job = db.query(AnalyticsExportJobDB).filter(AnalyticsExportJobDB.id == job_id, AnalyticsExportJobDB.tenant_id == tenant_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()
        try:
            filters = json.loads(job.filters_json or "{}")
            bot_id = filters.get("bot_id")
            convs = _scoped_conversations(db, tenant_id, bot_id=bot_id).all()

            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(["conversation_id", "bot_id", "status", "agent_requested", "created_at"])
            for c in convs:
                writer.writerow([c.id, c.bot_id, c.status, bool(c.agent_requested), c.created_at.isoformat()])
            job.artifact_csv = out.getvalue()
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)
            db.commit()
            logger.error("analytics_export_job_failed", extra={"tenant_id": tenant_id, "job_id": job_id, "error": str(exc)})
    finally:
        db.close()


@router.post("/reports/exports")
async def create_export_job(
    payload: ExportJobCreate,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    row = AnalyticsExportJobDB(
        tenant_id=tenant_id,
        requested_by=tenant_id,
        report_type=payload.report_type,
        filters_json=json.dumps(payload.filters or {}),
        status="queued",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    asyncio.create_task(_generate_export_artifact(tenant_id, row.id))
    return {"job_id": row.id, "status": row.status}


@router.post("/reports/schedules/{schedule_id}/run")
async def run_schedule_now(
    schedule_id: int,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    sched = (
        db.query(AnalyticsSnapshotScheduleDB)
        .filter(AnalyticsSnapshotScheduleDB.id == schedule_id, AnalyticsSnapshotScheduleDB.tenant_id == tenant_id)
        .first()
    )
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if not sched.is_active:
        raise HTTPException(status_code=409, detail="Schedule is inactive")

    job = AnalyticsExportJobDB(
        tenant_id=tenant_id,
        requested_by=tenant_id,
        report_type=sched.report_type,
        filters_json="{}",
        status="queued",
    )
    db.add(job)
    sched.last_run_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(job)
    asyncio.create_task(_generate_export_artifact(tenant_id, job.id))
    return {"schedule_id": schedule_id, "job_id": job.id, "status": "queued"}


@router.get("/reports/exports")
async def list_export_jobs(
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AnalyticsExportJobDB)
        .filter(AnalyticsExportJobDB.tenant_id == tenant_id)
        .order_by(AnalyticsExportJobDB.created_at.desc())
        .all()
    )
    return rows


@router.get("/reports/exports/{job_id}")
async def get_export_job(
    job_id: int,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    row = (
        db.query(AnalyticsExportJobDB)
        .filter(AnalyticsExportJobDB.id == job_id, AnalyticsExportJobDB.tenant_id == tenant_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Export job not found")
    return row


@router.get("/reports/exports/{job_id}/download")
async def download_export_job(
    job_id: int,
    tenant_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    row = (
        db.query(AnalyticsExportJobDB)
        .filter(AnalyticsExportJobDB.id == job_id, AnalyticsExportJobDB.tenant_id == tenant_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Export job not found")
    if row.status != "completed":
        raise HTTPException(status_code=409, detail="Export not ready")
    return {"job_id": row.id, "csv": row.artifact_csv or ""}
