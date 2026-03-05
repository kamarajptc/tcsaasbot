# Performance Baseline Tooling

Run the synthetic baseline for chat and ingest:

```bash
./backend/venv/bin/python backend/perf/run_baseline.py
```

Optional tuning parameters:

```bash
./backend/venv/bin/python backend/perf/run_baseline.py \
  --chat-requests 400 \
  --ingest-requests 240 \
  --chat-workers 16 \
  --ingest-workers 8
```

Artifacts are written to `backend/perf/reports/`:
- `baseline_<timestamp>.json`
- `LOAD_TEST_REPORT.md`

Run the live endpoint load suite against a running backend:

```bash
./backend/venv/bin/python backend/perf/run_load_suite.py \
  --base-url http://localhost:9100 \
  --username ops@tangentcloud.in \
  --password password123
```

Targets:
- `POST /api/v1/chat/public`
- `GET /api/v1/dashboard/conversations`
- `POST /api/v1/ingest/scrape`

Output artifact:
- `load_suite_<timestamp>.json`
