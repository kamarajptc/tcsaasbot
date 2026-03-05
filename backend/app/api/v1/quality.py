import asyncio
import json
import os
import re
import shutil
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging import logger
from app.core.security import get_current_user_context

router = APIRouter()

ROLE_ORDER = {"viewer": 1, "editor": 2, "admin": 3}
SENSITIVE_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}", re.IGNORECASE),
]


class RunTestsRequest(BaseModel):
    full: bool = True
    include_security_lane: bool = True
    parallel: bool = False
    max_fail: int = 0


class ChecklistUpdate(BaseModel):
    tests_green: Optional[bool] = None
    coverage_gate_passed: Optional[bool] = None
    vulnerabilities_reviewed: Optional[bool] = None
    migrations_reviewed: Optional[bool] = None
    rollback_ready: Optional[bool] = None
    notes: Optional[str] = None


def _require_role(context: dict, min_role: str):
    current = (context.get("role") or "admin").lower()
    if ROLE_ORDER.get(current, 0) < ROLE_ORDER[min_role]:
        raise HTTPException(status_code=403, detail="Insufficient role")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _safe_tenant(tenant_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.@-]", "_", tenant_id)


def _tenant_root(tenant_id: str) -> Path:
    root = _repo_root() / "docs" / "quality" / _safe_tenant(tenant_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _latest_dir(tenant_id: str) -> Path:
    d = _tenant_root(tenant_id) / "latest"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _history_dir(tenant_id: str) -> Path:
    d = _tenant_root(tenant_id) / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_file(tenant_id: str) -> Path:
    return _tenant_root(tenant_id) / "state.json"


def _checklist_file(tenant_id: str) -> Path:
    return _tenant_root(tenant_id) / "release_checklist.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2))


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _redact(text: str) -> str:
    result = text
    for pattern in SENSITIVE_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def _parse_junit(junit_path: Path) -> Dict[str, Any]:
    if not junit_path.exists():
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "duration_s": 0.0,
            "modules": [],
            "failures": [],
            "test_results": [],
        }
    root = ET.parse(junit_path).getroot()
    suite = root.find("testsuite") if root.tag != "testsuite" else root
    tests = int(suite.attrib.get("tests", "0"))
    failures = int(suite.attrib.get("failures", "0"))
    errors = int(suite.attrib.get("errors", "0"))
    skipped = int(suite.attrib.get("skipped", suite.attrib.get("skip", "0")))
    duration = float(suite.attrib.get("time", "0") or 0)
    passed = max(0, tests - failures - errors - skipped)

    modules: Dict[str, Dict[str, Any]] = {}
    failure_rows: List[Dict[str, Any]] = []
    test_results: List[Dict[str, Any]] = []
    for tc in suite.findall(".//testcase"):
        classname = tc.attrib.get("classname", "unknown")
        module = classname.split(".")[0] if "." in classname else classname
        test_id = f"{classname}::{tc.attrib.get('name', 'unknown')}"
        row = modules.setdefault(module, {"module": module, "total": 0, "failed": 0, "duration_s": 0.0})
        row["total"] += 1
        row["duration_s"] += float(tc.attrib.get("time", "0") or 0)
        fail_node = tc.find("failure") or tc.find("error")
        test_results.append({"test_id": test_id, "failed": fail_node is not None})
        if fail_node is not None:
            row["failed"] += 1
            failure_rows.append(
                {
                    "test_id": test_id,
                    "module": module,
                    "message": _redact((fail_node.attrib.get("message") or fail_node.text or "")[:1200]),
                }
            )
    modules_list = sorted(modules.values(), key=lambda x: (x["failed"], x["module"]), reverse=True)
    return {
        "total": tests,
        "passed": passed,
        "failed": failures,
        "errors": errors,
        "skipped": skipped,
        "duration_s": round(duration, 2),
        "modules": modules_list,
        "failures": failure_rows,
        "test_results": test_results,
    }


def _coverage_summary(latest: Path, junit_summary: Dict[str, Any]) -> Dict[str, Any]:
    cov_xml = latest / "coverage.xml"
    if cov_xml.exists():
        try:
            root = ET.parse(cov_xml).getroot()
            line_rate = float(root.attrib.get("line-rate", "0") or 0)
            pct = round(line_rate * 100, 2)
            return {"coverage_pct": pct, "source": "coverage.xml"}
        except Exception:
            pass
    total = junit_summary.get("total", 0) or 0
    passed = junit_summary.get("passed", 0) or 0
    proxy = round((passed / total) * 100, 2) if total > 0 else 0.0
    return {"coverage_pct": proxy, "source": "proxy_from_pass_rate"}


def _append_history(tenant_id: str, summary: Dict[str, Any]) -> None:
    history_file = _tenant_root(tenant_id) / "history.json"
    history = _read_json(history_file, {"runs": []}).get("runs", [])
    history.append(summary)
    history = history[-80:]
    _write_json(history_file, {"runs": history})


def _compute_flaky(tenant_id: str) -> List[Dict[str, Any]]:
    history = _read_json(_tenant_root(tenant_id) / "history.json", {"runs": []}).get("runs", [])
    by_test: Dict[str, List[bool]] = {}
    for run in history[-20:]:
        test_results = run.get("test_results", [])
        if not test_results:
            failed_ids = {f["test_id"] for f in run.get("failures", [])}
            for tid in failed_ids:
                by_test.setdefault(tid, []).append(True)
            continue
        for row in test_results:
            tid = row.get("test_id")
            if not tid:
                continue
            by_test.setdefault(tid, []).append(bool(row.get("failed")))
    rows = []
    for tid, states in by_test.items():
        if len(states) < 3:
            continue
        fail_count = sum(1 for s in states if s)
        if 0 < fail_count < len(states):
            rows.append(
                {
                    "test_id": tid,
                    "runs": len(states),
                    "failures": fail_count,
                    "flaky_score": round(fail_count / len(states), 3),
                    "quarantine_recommended": True,
                }
            )
    return sorted(rows, key=lambda x: x["flaky_score"], reverse=True)


async def _run_pytest_job(tenant_id: str, payload: RunTestsRequest):
    latest = _latest_dir(tenant_id)
    history = _history_dir(tenant_id)
    state = _state_file(tenant_id)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    state_data = {"run_id": run_id, "status": "running", "started_at": _now_iso()}
    _write_json(state, state_data)

    repo = _repo_root()
    junit = latest / "junit.xml"
    cmd = [str(repo / "backend" / "venv" / "bin" / "python"), "-m", "pytest", "-q", "backend/tests", f"--junitxml={junit}"]
    if payload.max_fail and payload.max_fail > 0:
        cmd.append(f"--maxfail={payload.max_fail}")

    # Optional parallel profile if xdist available.
    if payload.parallel:
        cmd.extend(["-n", "auto"])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(repo),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    output = _redact((out or b"").decode("utf-8", errors="ignore"))
    security_lane = {
        "executed": bool(payload.include_security_lane),
        "status": "skipped",
        "total": 0,
        "failed": 0,
        "duration_s": 0.0,
    }

    if payload.include_security_lane:
        security_junit = latest / "security_junit.xml"
        security_cmd = [
            str(repo / "backend" / "venv" / "bin" / "python"),
            "-m",
            "pytest",
            "-q",
            "backend/tests/test_auth_security.py",
            "backend/tests/test_release_uat_smoke.py",
            f"--junitxml={security_junit}",
        ]
        sec_proc = await asyncio.create_subprocess_exec(
            *security_cmd,
            cwd=str(repo),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        sec_out, _ = await sec_proc.communicate()
        security_log = _redact((sec_out or b"").decode("utf-8", errors="ignore"))
        output = f"{output}\n\n=== SECURITY LANE ===\n{security_log}"
        sec_summary = _parse_junit(security_junit)
        security_lane = {
            "executed": True,
            "status": "passed" if sec_proc.returncode == 0 else "failed",
            "total": sec_summary.get("total", 0),
            "failed": sec_summary.get("failed", 0) + sec_summary.get("errors", 0),
            "duration_s": sec_summary.get("duration_s", 0.0),
        }
    (latest / "pytest.log").write_text(output)

    junit_summary = _parse_junit(junit)
    coverage = _coverage_summary(latest, junit_summary)
    flaky = _compute_flaky(tenant_id)
    (latest / "flaky.json").write_text(json.dumps({"items": flaky}, indent=2))

    summary = {
        "run_id": run_id,
        "status": "completed" if proc.returncode == 0 and security_lane["status"] in {"passed", "skipped"} else "failed",
        "return_code": proc.returncode,
        "started_at": state_data["started_at"],
        "finished_at": _now_iso(),
        "pytest": junit_summary,
        "coverage": coverage,
        "security_lane": security_lane,
    }
    (latest / "summary.json").write_text(json.dumps(summary, indent=2))

    run_folder = history / run_id
    run_folder.mkdir(parents=True, exist_ok=True)
    for fname in ["summary.json", "junit.xml", "pytest.log", "flaky.json"]:
        src = latest / fname
        if src.exists():
            shutil.copy2(src, run_folder / fname)

    _append_history(tenant_id, {
        "run_id": run_id,
        "status": summary["status"],
        "finished_at": summary["finished_at"],
        "duration_s": summary["pytest"].get("duration_s", 0.0),
        "total": summary["pytest"].get("total", 0),
        "passed": summary["pytest"].get("passed", 0),
        "failed": summary["pytest"].get("failed", 0) + summary["pytest"].get("errors", 0),
        "failures": summary["pytest"].get("failures", []),
        "test_results": summary["pytest"].get("test_results", []),
        "modules": summary["pytest"].get("modules", []),
        "coverage_pct": summary["coverage"].get("coverage_pct", 0.0),
    })

    _write_json(state, {"run_id": run_id, "status": summary["status"], "finished_at": summary["finished_at"]})


def _service_status() -> List[Dict[str, Any]]:
    ports = [
        {"service": "backend", "port": 9100},
        {"service": "dashboard", "port": 9101},
        {"service": "mobile", "port": 9102},
    ]
    rows = []
    for p in ports:
        sock = None
        up = False
        try:
            import socket
            sock = socket.create_connection(("127.0.0.1", p["port"]), timeout=0.5)
            up = True
        except Exception:
            up = False
        finally:
            if sock:
                sock.close()
        rows.append(
            {
                "service": p["service"],
                "port": p["port"],
                "status": "up" if up else "down",
                "last_heartbeat": _now_iso(),
            }
        )
    return rows


def _parse_log_lines(limit: int = 3000) -> List[Dict[str, Any]]:
    repo = _repo_root()
    log_candidates = [repo / "backend.log", repo / "backend.out"]
    lines = []
    for path in log_candidates:
        if path.exists():
            try:
                data = path.read_text(errors="ignore").splitlines()[-limit:]
                lines.extend(data)
            except Exception:
                continue
    parsed = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if ln.startswith("{") and "\"message\"" in ln:
            try:
                obj = json.loads(ln)
                obj["raw"] = _redact(ln)
                parsed.append(obj)
                continue
            except Exception:
                pass
        parsed.append({"message": "unstructured", "raw": _redact(ln), "levelname": "INFO", "asctime": None})
    return parsed


def _alerts_from_logs(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    req = [x for x in logs if x.get("message") == "request_completed"]
    errs = [x for x in req if int(x.get("status_code", 200) or 200) >= 500]
    rate = (len(errs) / len(req) * 100.0) if req else 0.0
    alerts = []
    if rate >= 5.0:
        alerts.append({"severity": "high", "name": "High 5xx error rate", "value": round(rate, 2), "status": "triggered"})
    slow = [x for x in req if float(x.get("duration_ms", 0) or 0) >= 1500]
    if len(slow) >= 5:
        alerts.append({"severity": "medium", "name": "Slow request burst", "value": len(slow), "status": "triggered"})
    if not alerts:
        alerts.append({"severity": "info", "name": "No active alerts", "value": 0, "status": "ok"})
    return alerts


def _bool_check(name: str, passed: bool, details: Dict[str, Any]) -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "details": details}


@router.get("/rbac/me")
async def get_my_role(context: dict = Depends(get_current_user_context)):
    return {"tenant_id": context["tenant_id"], "role": context.get("role", "admin")}


@router.get("/status/services")
async def get_services_status(context: dict = Depends(get_current_user_context)):
    _require_role(context, "viewer")
    return {"items": _service_status()}


@router.post("/tests/run")
async def run_tests(
    payload: RunTestsRequest,
    context: dict = Depends(get_current_user_context),
):
    _require_role(context, "editor")
    tenant_id = context["tenant_id"]
    state = _read_json(_state_file(tenant_id), {})
    if state.get("status") == "running":
        raise HTTPException(status_code=409, detail="A test run is already in progress")
    asyncio.create_task(_run_pytest_job(tenant_id, payload))
    return {"ok": True, "status": "queued"}


@router.get("/tests/latest")
async def latest_test_summary(context: dict = Depends(get_current_user_context)):
    _require_role(context, "viewer")
    tenant_id = context["tenant_id"]
    latest = _latest_dir(tenant_id)
    summary = _read_json(latest / "summary.json", {})
    state = _read_json(_state_file(tenant_id), {"status": "idle"})
    return {"state": state, "summary": summary}


@router.get("/tests/modules")
async def latest_test_modules(context: dict = Depends(get_current_user_context)):
    _require_role(context, "viewer")
    tenant_id = context["tenant_id"]
    summary = _read_json(_latest_dir(tenant_id) / "summary.json", {})
    pytest_data = summary.get("pytest", {})
    return {"items": pytest_data.get("modules", []), "failures": pytest_data.get("failures", [])}


@router.get("/tests/trends")
async def test_trends(
    points: int = Query(default=20, ge=1, le=80),
    context: dict = Depends(get_current_user_context),
):
    _require_role(context, "viewer")
    tenant_id = context["tenant_id"]
    hist = _read_json(_tenant_root(tenant_id) / "history.json", {"runs": []}).get("runs", [])
    return {"items": hist[-points:]}


@router.get("/tests/flaky")
async def flaky_tests(context: dict = Depends(get_current_user_context)):
    _require_role(context, "viewer")
    tenant_id = context["tenant_id"]
    return {"items": _compute_flaky(tenant_id)}


@router.get("/tests/coverage")
async def coverage_status(context: dict = Depends(get_current_user_context)):
    _require_role(context, "viewer")
    tenant_id = context["tenant_id"]
    summary = _read_json(_latest_dir(tenant_id) / "summary.json", {})
    cov = summary.get("coverage", {"coverage_pct": 0.0, "source": "none"})
    gate = 75.0
    return {"coverage": cov, "gate_threshold_pct": gate, "gate_passed": float(cov.get("coverage_pct", 0.0)) >= gate}


@router.get("/observability/metrics")
async def observability_metrics(context: dict = Depends(get_current_user_context)):
    _require_role(context, "viewer")
    logs = _parse_log_lines()
    req = [x for x in logs if x.get("message") == "request_completed"]
    total = len(req)
    err = len([x for x in req if int(x.get("status_code", 200) or 200) >= 400])
    p95 = 0.0
    p99 = 0.0
    lats = sorted(float(x.get("duration_ms", 0) or 0) for x in req)
    if lats:
        p95 = lats[min(len(lats) - 1, int(0.95 * (len(lats) - 1)))]
        p99 = lats[min(len(lats) - 1, int(0.99 * (len(lats) - 1)))]
    return {
        "request_total": total,
        "error_total": err,
        "error_rate_pct": round((err / total * 100.0), 2) if total else 0.0,
        "latency_p95_ms": round(p95, 2),
        "latency_p99_ms": round(p99, 2),
    }


@router.get("/observability/logs")
async def observability_logs(
    level: Optional[str] = None,
    service: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    context: dict = Depends(get_current_user_context),
):
    _require_role(context, "viewer")
    logs = _parse_log_lines(limit=5000)
    level_u = (level or "").upper()
    rows = []
    for log in reversed(logs):
        lvl = (log.get("levelname") or "INFO").upper()
        raw = log.get("raw", "")
        if level_u and lvl != level_u:
            continue
        if service and service not in raw:
            continue
        rows.append(
            {
                "timestamp": log.get("asctime"),
                "level": lvl,
                "message": log.get("message"),
                "line": raw[:400],
            }
        )
        if len(rows) >= limit:
            break
    return {"items": rows}


@router.get("/observability/traces")
async def observability_traces(
    limit: int = Query(default=50, ge=1, le=200),
    context: dict = Depends(get_current_user_context),
):
    _require_role(context, "viewer")
    logs = _parse_log_lines(limit=5000)
    req = [x for x in logs if x.get("message") == "request_completed"]
    req.sort(key=lambda x: float(x.get("duration_ms", 0) or 0), reverse=True)
    rows = []
    for x in req[:limit]:
        rows.append(
            {
                "path": x.get("path"),
                "status_code": x.get("status_code"),
                "duration_ms": x.get("duration_ms"),
                "trace_id": x.get("trace_id"),
                "span_id": x.get("span_id"),
            }
        )
    return {"items": rows}


@router.get("/observability/alerts")
async def observability_alerts(context: dict = Depends(get_current_user_context)):
    _require_role(context, "viewer")
    logs = _parse_log_lines(limit=5000)
    return {"items": _alerts_from_logs(logs)}


@router.get("/release/checklist")
async def get_release_checklist(context: dict = Depends(get_current_user_context)):
    _require_role(context, "viewer")
    tenant_id = context["tenant_id"]
    default = {
        "tests_green": False,
        "coverage_gate_passed": False,
        "vulnerabilities_reviewed": False,
        "migrations_reviewed": False,
        "rollback_ready": False,
        "notes": "",
        "updated_at": None,
    }
    return _read_json(_checklist_file(tenant_id), default)


@router.put("/release/checklist")
async def update_release_checklist(
    payload: ChecklistUpdate,
    context: dict = Depends(get_current_user_context),
):
    _require_role(context, "editor")
    tenant_id = context["tenant_id"]
    current = _read_json(_checklist_file(tenant_id), {})
    for k, v in payload.model_dump(exclude_unset=True).items():
        current[k] = v
    current["updated_at"] = _now_iso()
    _write_json(_checklist_file(tenant_id), current)
    return {"ok": True, "checklist": current}


@router.get("/release/risk")
async def release_risk(context: dict = Depends(get_current_user_context)):
    _require_role(context, "viewer")
    tenant_id = context["tenant_id"]
    summary = _read_json(_latest_dir(tenant_id) / "summary.json", {})
    pytest_data = summary.get("pytest", {})
    total = pytest_data.get("total", 0) or 0
    failed = (pytest_data.get("failed", 0) or 0) + (pytest_data.get("errors", 0) or 0)
    fail_ratio = (failed / total) if total else 1.0
    flaky = _compute_flaky(tenant_id)
    alerts = _alerts_from_logs(_parse_log_lines(limit=4000))
    critical_alerts = len([a for a in alerts if a.get("severity") == "high" and a.get("status") == "triggered"])
    score = 100.0
    score -= min(60.0, fail_ratio * 100.0)
    score -= min(20.0, len(flaky) * 2.0)
    score -= min(20.0, critical_alerts * 10.0)
    score = round(max(0.0, score), 2)
    return {"risk_score": score, "failed_tests": failed, "flaky_count": len(flaky), "critical_alerts": critical_alerts}


@router.get("/release/evidence")
async def release_evidence(context: dict = Depends(get_current_user_context)):
    _require_role(context, "admin")
    tenant_id = context["tenant_id"]
    troot = _tenant_root(tenant_id)
    evidence = troot / "evidence_bundle.zip"
    with zipfile.ZipFile(evidence, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in [
            Path("latest/summary.json"),
            Path("latest/junit.xml"),
            Path("latest/pytest.log"),
            Path("latest/flaky.json"),
            Path("release_checklist.json"),
            Path("history.json"),
        ]:
            src = troot / rel
            if src.exists():
                zf.write(src, arcname=str(rel))
    return {"path": str(evidence), "size_bytes": evidence.stat().st_size if evidence.exists() else 0}


@router.post("/retention/apply")
async def retention_apply(
    days: int = Query(default=30, ge=1, le=365),
    context: dict = Depends(get_current_user_context),
):
    _require_role(context, "admin")
    tenant_id = context["tenant_id"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    hdir = _history_dir(tenant_id)
    removed = 0
    for child in hdir.iterdir():
        if not child.is_dir():
            continue
        try:
            ts = datetime.strptime(child.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            if ts < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        except Exception:
            continue
    logger.info("quality_retention_applied", extra={"tenant_id": tenant_id, "days": days, "removed_runs": removed})
    return {"ok": True, "removed_runs": removed}


@router.get("/security/checklist")
async def security_checklist(context: dict = Depends(get_current_user_context)):
    _require_role(context, "viewer")
    settings = get_settings()
    env = (settings.ENV or "").strip().lower()
    is_prod = env in {"prod", "production"}

    checks = [
        _bool_check(
            "api_key_auth_disabled",
            not settings.ALLOW_API_KEY_AUTH,
            {"allow_api_key_auth": settings.ALLOW_API_KEY_AUTH},
        ),
        _bool_check(
            "auth_password_not_default_in_prod",
            (not is_prod) or settings.AUTH_PASSWORD != "password123",
            {"env": env, "auth_password_default": settings.AUTH_PASSWORD == "password123"},
        ),
        _bool_check(
            "secret_key_not_default_in_prod",
            (not is_prod) or settings.SECRET_KEY != "TCSAASBOT_SUPER_SECRET_KEY_CHANGE_IN_PROD",
            {"env": env, "secret_key_default": settings.SECRET_KEY == "TCSAASBOT_SUPER_SECRET_KEY_CHANGE_IN_PROD"},
        ),
        _bool_check(
            "jwt_ttl_within_24h",
            int(settings.ACCESS_TOKEN_EXPIRE_MINUTES) <= 1440,
            {"access_token_expire_minutes": int(settings.ACCESS_TOKEN_EXPIRE_MINUTES)},
        ),
        _bool_check(
            "auth_requires_existing_tenant",
            bool(settings.AUTH_REQUIRE_EXISTING_TENANT),
            {"auth_require_existing_tenant": settings.AUTH_REQUIRE_EXISTING_TENANT},
        ),
    ]
    passed = all(c["passed"] for c in checks)
    return {
        "tenant_id": context["tenant_id"],
        "env": env or "development",
        "passed": passed,
        "checks": checks,
    }
