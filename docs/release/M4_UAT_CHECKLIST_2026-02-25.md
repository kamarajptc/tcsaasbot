# M4 UAT Checklist (Completed)

Date: 2026-02-25
Release: M4 Mobile & Scale
Owner: Engineering

## Exit Criteria
- [x] Critical automated tests are green.
- [x] UAT smoke flow for bot, knowledge, chat, leads, transfer, and integrations is green.
- [x] Performance baseline report for chat and ingest is generated.
- [x] Rollback runbook is documented and reviewed.

## Automated Validation Evidence
- Critical regression command:
  - `./backend/venv/bin/python -m pytest -q backend/tests/test_auth_security.py backend/tests/test_api.py backend/tests/test_live_chat_screen.py backend/tests/test_billing_quota.py backend/tests/test_ai_suggestions.py backend/tests/test_agent_transfer.py backend/tests/test_integrations_api.py`
  - Result: `72 passed`.
- UAT smoke command:
  - `./backend/venv/bin/python -m pytest -q backend/tests/test_release_uat_smoke.py`
  - Result: `2 passed`.

## UAT Scope Coverage
- [x] Auth and tenant safety gates
- [x] Bot create/update/read
- [x] Knowledge ingest/list
- [x] Chat request/response
- [x] Lead capture
- [x] Agent transfer rule trigger path
- [x] Integrations persistence
- [x] Shopify order lookup action
- [x] Slack event hooks for leads/transfer

## Performance Evidence
- Report: `backend/perf/reports/LOAD_TEST_REPORT.md`
- Raw data: `backend/perf/reports/baseline_20260225_100243.json`

## Signoff
- Engineering signoff: Approved
- QA signoff: Approved (automated UAT smoke + critical suite)
- Rollback readiness: Approved
