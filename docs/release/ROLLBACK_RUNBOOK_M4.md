# Rollback Runbook (M4)

Date: 2026-02-25
Target: M4 Mobile & Scale release rollback procedure

## Triggers
- Elevated 5xx error rate on chat/ingest APIs
- Data corruption in integrations or transfer-rule paths
- Auth failures after deployment
- Sustained latency regression beyond agreed SLO

## Pre-Rollback Checklist
- Confirm incident severity and blast radius.
- Announce deployment freeze in incident channel.
- Capture current deploy version and latest successful version.
- Snapshot database before rollback when possible.

## Rollback Steps
1. Stop traffic shift / disable new deploy.
2. Re-deploy previous stable backend artifact.
3. Re-deploy previous stable dashboard/mobile bundles if release included client changes.
4. Verify migrations are backward-compatible.
5. Run quick health validation:
   - `GET /`
   - `POST /api/v1/chat/`
   - `POST /api/v1/ingest/`
   - `GET /api/v1/integrations/bots/{bot_id}/integrations`
6. Run targeted smoke tests:
   - `./backend/venv/bin/python -m pytest -q backend/tests/test_release_uat_smoke.py`

## Data Rollback Guidance
- If schema changes are additive only, prefer application rollback without DB rollback.
- If destructive migration occurred, restore from pre-deploy snapshot and replay validated events only.

## Post-Rollback Verification
- Check error rate and latency for 30 minutes.
- Verify lead capture and transfer notifications are functioning.
- Verify Shopify lookup endpoint returns expected results.
- Document timeline, root cause, and follow-up actions.

## Communication Template
- "Rollback initiated for M4 at <timestamp UTC>. Cause: <short reason>. ETA to stabilize: <minutes>."
- "Rollback completed at <timestamp UTC>. Monitoring for <N> minutes before incident closure."
