# Text.com-Inspired Chat Analytics Product Roadmap

Date: 2026-02-25

## 1) Input Analysis (Text.com)

Based on Text.com product/help pages, the recurring analytics capabilities are:
- Unified reporting across chats, tickets, AI agent, and teammates.
- Core chat metrics: total chats, missed chats, response times, chat duration, engagement/coverage.
- CSAT segmentation: automated, manual, assisted.
- Operational filters and segmentation: teammate, tag, assignment, availability, country, keyword.
- Comparisons and trend analysis by period.
- Export and API access for analytics data.

## 2) Product Vision

Build a "Chat Analytics & Service Intelligence" module that gives support leaders real-time visibility into:
- Demand (chat/ticket volume and trends)
- Service quality (response times, CSAT)
- AI effectiveness (deflection, transfer, assisted outcomes)
- Team coverage and performance (availability, workload, productivity)

## 3) Feature Set

### Foundation Features
- Unified Metrics Overview Dashboard
- Time-range trends (hour/day/week/month)
- Segment filters (bot, channel, teammate, tag, country, assignment)
- CSV export for any report

### Chat Analytics
- Total chats
- Missed/unreplied chats
- First response time and median response time
- Chat duration (queue/wait vs active handling)
- Coverage (online vs offline distribution)

### AI Analytics
- Deflection rate (resolved without handoff)
- Transfer rate (AI to human)
- Assisted conversation rate (hybrid AI+human)
- AI resolution quality proxy (by outcome + CSAT)
- Top intents/topics from conversation mining

### Team Analytics
- Teammate performance (FRT, chats handled, CSAT)
- Teammate activity/availability timeline
- Load balancing view (queue pressure vs active capacity)

### Ticket Analytics
- New tickets vs solved tickets
- Ticket resolution time
- Ticket CSAT and ranking
- Source/channel mix

### Data & Platform
- Analytics API v1 (internal + external BI)
- Scheduled report snapshots
- Alerting thresholds (latency spike, CSAT drop, missed chat spike)

## 4) Milestones

### Milestone M1: Analytics Foundation (4 weeks)
- KPI cards + trend charts
- Data model for conversations/messages/outcomes
- Basic filters + CSV export
- Acceptance: leadership dashboard available and validated with fixture data

### Milestone M2: AI + Chat Performance Intelligence (4 weeks)
- AI deflection/transfer/assisted metrics
- Response-time and missed-chat reliability metrics
- Top intents/topics extraction
- Acceptance: no mock metrics; all computed from lifecycle data

### Milestone M3: Team Operations and Alerts (4 weeks)
- Teammate performance/activity dashboards
- Coverage and staffing gaps view
- Alert rules and notification channels
- Acceptance: proactive alerting for SLA/quality regressions

### Milestone M4: Reporting API + Enterprise Readiness (4-6 weeks)
- Public/internal analytics endpoints
- Metric dictionary and governance
- Snapshot jobs, export jobs, retention rules
- Acceptance: external BI ingestion enabled and documented

## 5) Delivery Plan (Sprints)

### Sprint 1
- Metrics schema and event contracts
- Summary + trend endpoints
- Dashboard skeleton

### Sprint 2
- Chat metrics (volume, missed, FRT, duration)
- Filtering + comparisons
- CSV export

### Sprint 3
- AI metrics (deflection/transfer/assisted)
- Topic mining and transfer reasons
- Data-quality tests for edge cases

### Sprint 4
- Teammate analytics + coverage model
- Alerting baseline + dashboards
- API hardening + docs

## 6) Jira-Ready User Stories

### Epic A: Core Analytics
- US-A1: As a support manager, I can view total chats, missed chats, and response-time trends by date range.
  - AC: charts support daily/hourly aggregation; values match fixture totals.
- US-A2: As an analyst, I can filter analytics by teammate, tag, channel, and country.
  - AC: filters apply consistently across all dashboard widgets.
- US-A3: As an ops user, I can export report data to CSV.
  - AC: export honors active filters and selected date range.

### Epic B: AI Effectiveness
- US-B1: As a manager, I can see AI deflection, transfer, and assisted rates.
  - AC: rates are computed from conversation lifecycle state, not static defaults.
- US-B2: As a QA lead, I can inspect recent transfer conversations and reasons.
  - AC: transfer list includes timestamp, conversation ID, and last user message snippet.
- US-B3: As a product owner, I can see top recurring intents from chat text.
  - AC: top intents are extracted from user message patterns with counts.

### Epic C: Team Performance
- US-C1: As a support lead, I can view teammate FRT, handled volume, and CSAT.
  - AC: teammate leaderboard updates for selected period.
- US-C2: As a workforce manager, I can view online/available coverage timeline.
  - AC: gaps are identifiable by hourly availability visualization.

### Epic D: Tickets and Resolution
- US-D1: As a service manager, I can track new, solved, and closed tickets over time.
  - AC: metrics reconcile with ticket table totals.
- US-D2: As QA, I can compare chat CSAT vs ticket CSAT and by handling mode.
  - AC: automated/manual/assisted CSAT segments are displayed.

### Epic E: API and Governance
- US-E1: As a data engineer, I can query analytics via API with filters/date range.
  - AC: endpoint supports pagination, filters, and deterministic response schema.
- US-E2: As a platform owner, I can audit metric definitions and calculation versions.
  - AC: each metric includes formula/version metadata in docs.
- US-E3: As an SRE, I receive alerts when critical service metrics regress.
  - AC: alerts trigger for thresholds on missed chats, FRT, and CSAT drop.

## 7) Non-Functional Requirements
- Data freshness: <= 5 min for operational dashboards.
- Reliability: >= 99.9% report endpoint availability.
- Performance: P95 dashboard API response <= 800 ms for default range.
- Security: tenant-scoped access and audit logs for report exports/API calls.
- Quality: automated reconciliation tests between raw events and computed metrics.

## 8) Recommended KPIs
- Deflection rate
- Transfer rate
- Assisted rate
- Missed chat rate
- First response time (P50/P95)
- Chat and ticket CSAT
- Coverage ratio (online demand vs staffed availability)
- Solve/close throughput

## Source Links
- https://www.text.com/help/reports-overview/
- https://www.text.com/help/chats-reports/
- https://www.text.com/help/teammates-reports/
- https://www.text.com/features/ai-live-chat/
- https://www.text.com/features/ai-help-desk/
- https://www.text.com/features/inbox/
- https://platform.text.com/docs/data-reporting/reports-api/v2.0

## Current App Alignment (TCSAASBOT)

This roadmap is now mapped to your current modules:
- Chat runtime: `backend/app/api/v1/chat.py`
- Analytics: `backend/app/api/v1/analytics.py`
- Leads: `backend/app/api/v1/leads.py`
- Dashboard settings/reports UI: `dashboard/components/Settings.tsx`, `dashboard/components/AIReport.tsx`, `dashboard/components/ConversationLog.tsx`
- Monitoring stack: `monitoring/grafana/*`, Loki/Promtail config

### Already Implemented in Current App
- Tenant-safe chat/ingest/conversation access controls
- Lead capture with bot+conversation metadata
- SMTP notification reliability improvements
- Live chat status flow (`new/open/pending/resolved`) and filtering
- AI performance from lifecycle metrics (deflection/transfer/trend/recent transfers)
- Tool governance baseline (allowlist + tool call audit logs)
- Flow runtime matching for active bot nodes in chat path
- Monitoring dashboard baseline for errors/latency/business counters

### Next Product Milestones (Application-Specific)
- M5: Advanced Team Analytics
  - teammate workload, SLA breach risk, staffing recommendations
- M6: Conversation Quality Intelligence
  - intent clusters with confidence, failed-answer detection, coaching suggestions
- M7: Enterprise Reporting
  - scheduled report delivery, metric dictionary endpoint, BI connector hardening

### Jira Story Candidates (Next Set)
- As support lead, I can view teammate-level FRT P50/P95 and handled sessions by shift.
- As QA manager, I can see unresolved-conversation reasons grouped by intent and bot.
- As ops, I can configure alerts for CSAT drop, missed-chat spike, and transfer-rate anomalies.
- As analyst, I can schedule daily/weekly analytics snapshots to email/Slack.
- As enterprise customer, I can fetch all analytics via stable paginated API with schema versioning.
