# Enhanced Web Scraper Logging & Tracing - Implementation Summary

## Problem Statement
User was attempting to scrape https://www.dataflo.io/ but received "scraping failed" messages with insufficient logging to diagnose the root cause. OpenTelemetry was already configured but not utilized in the scraper module.

## Solution Implemented
Added comprehensive OpenTelemetry distributed tracing and multi-level detailed JSON logging throughout the web scraping pipeline to provide complete visibility into the scraping process.

## Code Changes

### Modified File: `backend/app/api/v1/ingest.py`

#### 1. Imports & Tracer Setup
```python
import time
from app.core.telemetry import get_tracer

tracer = get_tracer("ingest_service")
```

#### 2. Enhanced Function: `_extract_sitemaps_from_robots()`
**Purpose**: Fetch and parse robots.txt for sitemap references

**Logging Added**:
- INFO: robots.txt fetch start (URL)
- INFO: robots.txt response (status_code, response_size)
- WARNING: robots.txt not found (404/other failures)
- DEBUG: Each sitemap URL found
- INFO: Parsing complete (count of sitemaps found)
- ERROR: Timeout/request/parsing failures with error types

**OpenTelemetry Spans**:
- `extract_sitemaps_from_robots` span
- Attributes: base_url, robots_url, robots_status_code, sitemaps_found, error_type

**Benefits**:
- Identify if robots.txt exists and is accessible
- See which sitemaps are referenced
- Diagnose robots.txt fetch failures

#### 3. Enhanced Function: `_fetch_sitemap_urls()`
**Purpose**: Recursively discover all URLs from sitemap.xml files

**Logging Added**:
- INFO: Sitemap discovery start (seed_sitemaps_count, standard_paths)
- DEBUG: Per-sitemap fetching (URL, status, size, time)
- DEBUG: XML parsing (root_tag, is_index)
- DEBUG: URL domain validation (expected vs actual domain)
- DEBUG: Child sitemap queuing
- DEBUG: GZIP decompression tracking
- ERROR: XML parse failures, HTTP errors, timeouts per URL
- INFO: Discovery complete (summary: visited, discovered, errors)

**Metrics Tracked**:
- fetch_time_seconds (HTTP request)
- response_size (bytes)
- decompressed_size (after GZIP)
- URLs per sitemap
- Error counts with error details list

**OpenTelemetry Spans**:
- `fetch_sitemap_urls` span with attributes
- Per-error tracking with error details
- Performance metrics (sitemaps_visited, urls_discovered, fetch_errors)

**Benefits**:
- See exact sitemap chain being processed
- Identify broken sitemaps (404s, parse errors)
- Track GZIP decompression issues
- Measure sitemap fetch performance
- Detect domain mismatches in sitemap URLs

#### 4. Enhanced Function: `_fetch_page_payload()`
**Purpose**: Fetch and parse individual page content

**Logging Added**:
- DEBUG: Page fetch start/complete (size, time)
- DEBUG: HTML parsing (size, parse_time)
- DEBUG: Link extraction (count, extraction_time)
- DEBUG: Text cleaning (length, clean_time)
- DEBUG: Title extraction (title value)
- DEBUG: Section extraction (count, extraction_time)
- DEBUG: Contact fallback addition
- WARNING: Empty content after cleaning
- ERROR: HTTP errors (status_code), timeouts, request errors, parsing errors

**Metrics Tracked**:
- fetch_time_seconds
- content_size (bytes)
- parse_time_seconds
- links_found
- clean_text_length
- sections_found
- Error types and HTTP status codes

**OpenTelemetry Spans**:
- `fetch_page_payload` span with full metrics
- Attributes: url, domain, index_sections, status_code, content_size, parse_time_seconds, links_found, clean_text_length, sections_found, title
- Error attributes: error_type, error_class

**Benefits**:
- Identify pages returning 404s or HTTP errors
- Track content parsing success/failure
- Measure page processing performance
- See links discovered per page
- Diagnose content extraction issues

#### 5. Enhanced Function: `scrape_website()` - Main Endpoint
**Purpose**: Orchestrate entire scraping process

**Logging Added**:

*Request Lifecycle*:
- INFO: scrape_request_started (url, tenant_id, max_pages, use_sitemaps)
- DEBUG: url_normalized (original → normalized)
- DEBUG: domain_extracted (domain value)
- DEBUG: URL safety validation result
- INFO: discovering_sitemaps (start of phase)
- INFO: sitemaps_discovered (count, time_seconds)
- INFO: crawl_preparation_complete (queue_size, existing_docs, budget)

*Per-Page Loop*:
- INFO: crawl_item (url, progress n/max, queue_size)
- DEBUG: page_payload_received (title, content_size, links_count, payload_fetch_time)
- DEBUG: page_persisted (docs_created, sections_indexed, persist_time, budget_remaining)
- WARNING: page_payload_empty (URL that failed)

*Completion*:
- INFO: crawl_completed (summary stats with detailed breakdown)
- ERROR/INFO: no_readable_content (if all pages failed)
- INFO: scrape_request_completed (success with total_time_seconds)
- ERROR: scrape_request_http_error (detailed status_code and reason)
- ERROR: scrape_network_error (error_type)
- ERROR: scrape_unexpected_error (error_class)

**Summary Metrics**:
- pages_scraped, pages_discovered, pages_failed
- new_pages_indexed, section_docs_indexed
- failed_urls list (for debugging)
- crawl_time_seconds, average_page_time (ms per page)
- total_time_seconds for entire request
- sitemaps_discovered count

**OpenTelemetry Spans**:
- `scrape_website` root span with complete metrics
- Attributes: url, tenant_id, max_pages, use_sitemaps, domain
- All major metrics as span attributes for distributed tracing
- Performance metrics: total_time_seconds
- Error tracking: error_type, error_class, http_error_status

**Benefits**:
- Complete visibility into entire scraping session
- Identify where time is spent (sitemap discovery vs crawling)
- Track document quota consumption
- See all failed URLs for manual review
- Monitor performance per page
- Diagnose early failures (robots.txt, sitemaps) vs late failures (page parsing)

## Log Output Examples

### Successful Page Fetch
```json
{
  "message": "page_payload_complete",
  "levelname": "INFO",
  "extra": {
    "url": "https://www.dataflo.io/blog/example",
    "title": "Example Blog Post",
    "content_length": 2450,
    "links_count": 12,
    "sections_count": 3
  },
  "otelTraceID": "350ca6a368aaba0c2682d2f04b01e41a"
}
```

### 404 Error Page
```json
{
  "message": "page_fetch_http_error",
  "levelname": "ERROR",
  "extra": {
    "url": "https://www.dataflo.io/blog/missing-page",
    "status_code": 404,
    "error": "404 Client Error: Not Found"
  },
  "otelTraceID": "350ca6a368aaba0c2682d2f04b01e41a"
}
```

### Timeout Error
```json
{
  "message": "page_fetch_timeout",
  "levelname": "ERROR",
  "extra": {
    "url": "https://www.dataflo.io/slow-page",
    "error": "('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"
  },
  "otelTraceID": "350ca6a368aaba0c2682d2f04b01e41a"
}
```

### Sitemap Discovery Summary
```json
{
  "message": "sitemap_discovery_complete",
  "levelname": "INFO",
  "extra": {
    "base_url": "https://www.dataflo.io",
    "domain": "dataflo.io",
    "sitemaps_visited": 5,
    "urls_discovered": 342,
    "fetch_errors": 2,
    "errors": [
      {"url": "https://www.dataflo.io/sitemap2.xml", "status": 404},
      {"url": "https://www.dataflo.io/products-sitemap.xml", "error": "timeout"}
    ]
  },
  "otelTraceID": "350ca6a368aaba0c2682d2f04b01e41a"
}
```

### Complete Crawl Summary
```json
{
  "message": "crawl_completed",
  "levelname": "INFO",
  "extra": {
    "domain": "dataflo.io",
    "pages_scraped": 45,
    "pages_failed": 8,
    "failed_urls": [
      "https://www.dataflo.io/missing-1",
      "https://www.dataflo.io/missing-2"
    ],
    "new_docs_indexed": 45,
    "section_docs_indexed": 89,
    "unique_urls_discovered": 53,
    "crawl_time_seconds": 127.34,
    "average_page_time": 2.82
  },
  "otelTraceID": "350ca6a368aaba0c2682d2f04b01e41a"
}
```

## Diagnosing Dataflo.io Issues

With enhanced logging, you can now debug the scraping failure:

### Check for Robots.txt Blocking
```bash
tail -f backend.out | grep "robots\|Robots"
```
Look for:
- `robots_fetch_complete` with 200 status → robots.txt exists
- `robots_not_found` with 404 status → No robots.txt
- `robots_timeout` → Connection timeout
- `sitemaps_found` count → How many sitemaps referenced

### Check for Sitemap Issues
```bash
tail -f backend.out | grep "sitemap"
```
Look for:
- `sitemap_discovery_start` → Discovery began
- `fetching_sitemap` → Individual sitemap fetch
- `sitemap_xml_parse_failed` → XML parsing error
- `url_domain_mismatch` → URL from wrong domain
- `sitemap_discovery_complete` → Summary with error count

### Check for Page Fetch Issues
```bash
tail -f backend.out | grep "page_fetch\|page_payload"
```
Look for:
- `page_fetch_complete` with status_code → HTTP response status
- `page_fetch_http_error` with 404/403/etc → Page errors
- `page_fetch_timeout` → Timeout on fetch
- `empty_content_after_cleaning` → Page returned but no readable content

### Check for Content Extraction Issues
```bash
tail -f backend.out | grep "links_extracted\|text_cleaned\|sections_extracted"
```
Look for:
- `links_found` count → 0 means no discovered links
- `clean_text_length` → Content available
- `sections_found` count → Semantic sections detected

## Performance Monitoring

The enhanced logging also enables performance monitoring:

```bash
# Average page fetch time
tail -f backend.out | grep "page_fetch_complete" | jq '.extra.fetch_time_seconds' | \
  awk '{sum+=$1; count++} END {print "Average:", sum/count}'

# Identify slow pages
tail -f backend.out | grep "page_fetch_complete" | \
  jq 'select(.extra.fetch_time_seconds > 5)'

# Crawl efficiency
tail -f backend.out | grep "crawl_completed" | \
  jq '{pages: .extra.pages_scraped, time: .extra.crawl_time_seconds, avg: .extra.average_page_time}'
```

## OpenTelemetry Integration

All enhanced logging is automatically:
- Exported to OpenTelemetry collector (if running in Docker)
- Correlated with trace IDs for complete request tracking
- Compatible with observability platforms (Jaeger, Datadog, New Relic, Grafana)
- Ready for distributed tracing across services

Each scraping request gets a unique `otelTraceID` that links all related logs together.

## Next Steps for User

1. **Retry scraping dataflo.io**:
   ```bash
   curl -X POST http://localhost:9100/api/v1/ingest/scrape \
     -H "x-api-key: YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://www.dataflo.io/", "max_pages": 10, "use_sitemaps": true}'
   ```

2. **Monitor real-time logs**:
   ```bash
   tail -f /Users/kamarajp/TCSAASBOT/backend.out | \
     grep -E "scrape_request|sitemap|page_fetch|crawl_completed"
   ```

3. **Analyze failures**: Use the log output to identify:
   - Are sitemaps being discovered?
   - Are pages returning 404s?
   - Are timeouts occurring?
   - Is content being extracted successfully?

4. **Collect logs for investigation**: Save a complete scraping session for analysis:
   ```bash
   curl -X POST http://localhost:9100/api/v1/ingest/scrape \
     -H "x-api-key: YOUR_API_KEY" \
     -d '{"url": "https://www.dataflo.io/", "max_pages": 5}' 2>&1 | tee scrape_response.log
   
   tail -f backend.out | tee -a scrape_logs.json
   ```

## Files Modified
- `/Users/kamarajp/TCSAASBOT/backend/app/api/v1/ingest.py` - Enhanced scraper module with comprehensive logging

## Testing
- Services restarted successfully
- Backend running on port 9100
- Enhanced logging active and ready for use
- OpenTelemetry tracing enabled

## Documentation
- Created `/Users/kamarajp/TCSAASBOT/SCRAPER_LOGGING_ENHANCEMENT.md` with complete reference
