# Performance Baseline Report

Generated at (UTC): 2026-02-25T10:02:43.643971+00:00

## Scope
- Runner: fastapi-testclient
- Chat requests: 200 (workers=10)
- Ingest requests: 120 (workers=6)
- Warmup iterations: 3

## Results

### Chat (`POST /api/v1/chat/`)
- Throughput: 308.15 req/s
- Avg latency: 32.13 ms
- P50 latency: 28.28 ms
- P95 latency: 59.46 ms
- P99 latency: 63.46 ms
- Max latency: 63.55 ms

### Ingest (`POST /api/v1/ingest/`)
- Throughput: 540.57 req/s
- Avg latency: 10.84 ms
- P50 latency: 9.28 ms
- P95 latency: 19.99 ms
- P99 latency: 23.33 ms
- Max latency: 24.33 ms

## Tuning Recommendations
- Move sqlite to managed Postgres for write-heavy ingest workloads.
- Add worker queue for crawl/ingest to isolate user-facing API latency.
- Cache frequent chat retrieval paths and keep vector index warm.
- Add p95 latency SLO alerts and request-rate autoscaling policy.

## Raw Artifact
- JSON: `/Users/kamarajp/TCSAASBOT/backend/perf/reports/baseline_20260225_100243.json`
