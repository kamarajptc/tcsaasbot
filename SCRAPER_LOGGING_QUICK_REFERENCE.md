# Quick Reference: Enhanced Scraper Logging

## Real-Time Monitoring Commands

### Watch All Scraper Activities
```bash
tail -f /Users/kamarajp/TCSAASBOT/backend.out | \
  grep -E "scrape_request|sitemap|crawl|page_fetch"
```

### Watch Only Errors
```bash
tail -f /Users/kamarajp/TCSAASBOT/backend.out | \
  grep '"levelname": "ERROR"'
```

### Watch Sitemap Discovery
```bash
tail -f /Users/kamarajp/TCSAASBOT/backend.out | \
  grep -i "sitemap"
```

### Watch Page Fetching
```bash
tail -f /Users/kamarajp/TCSAASBOT/backend.out | \
  grep -E "page_fetch|page_payload|page_processing"
```

### Watch Request Lifecycle
```bash
tail -f /Users/kamarajp/TCSAASBOT/backend.out | \
  grep -E "scrape_request_started|scrape_request_completed|scrape_request_http_error"
```

### Filter by Specific URL
```bash
tail -f /Users/kamarajp/TCSAASBOT/backend.out | \
  grep "dataflo.io"
```

## Analyzing Completed Scrapes

### Show All Failed URLs
```bash
grep "crawl_completed" /Users/kamarajp/TCSAASBOT/backend.out | tail -1 | \
  jq '.extra.failed_urls'
```

### Show Scrape Summary (Last Run)
```bash
grep "scrape_request_completed" /Users/kamarajp/TCSAASBOT/backend.out | tail -1 | \
  jq '.extra'
```

### Show Crawl Statistics (Last Run)
```bash
grep "crawl_completed" /Users/kamarajp/TCSAASBOT/backend.out | tail -1 | \
  jq '.extra | {pages_scraped, pages_failed, new_docs, time_seconds}'
```

### Show All Sitemap Errors
```bash
grep "sitemap" /Users/kamarajp/TCSAASBOT/backend.out | \
  grep "ERROR\|error" | \
  jq '.extra'
```

### Show All Page Fetch Errors
```bash
grep "page_fetch" /Users/kamarajp/TCSAASBOT/backend.out | \
  grep "ERROR\|error" | \
  jq '.extra.url, .extra.error, .extra.status_code'
```

## Common Issues & How to Find Them

### Issue: "No readable content found"
**Look for**:
```bash
grep "no_readable_content\|empty_content_after_cleaning" /Users/kamarajp/TCSAASBOT/backend.out
```
**What it means**: All pages either failed or had no extractable text
**Solution**: Check page_fetch logs to see which pages returned empty content

### Issue: "Scraping Failed" with No Details
**Look for**:
```bash
grep "scrape_request_http_error\|scrape_network_error\|scrape_unexpected_error" /Users/kamarajp/TCSAASBOT/backend.out | tail -5
```
**What it means**: Request failed at HTTP level, network level, or unexpected exception
**Solution**: Check the error message and error_type for root cause

### Issue: Only 1-2 Pages Scraped Instead of Hundreds
**Look for**:
```bash
grep "sitemap_discovery_complete\|sitemaps_discovered" /Users/kamarajp/TCSAASBOT/backend.out
```
**What it means**: Sitemap discovery found very few URLs
**Solution**: Check if robots.txt has sitemaps and if sitemaps are accessible

### Issue: Many 404 Errors
**Look for**:
```bash
grep "page_fetch_http_error.*404" /Users/kamarajp/TCSAASBOT/backend.out | wc -l
```
**What it means**: Many discovered URLs return 404 (page not found)
**Solution**: URLs in sitemap may be outdated or there's a domain mismatch

### Issue: Timeouts
**Look for**:
```bash
grep "timeout\|Timeout" /Users/kamarajp/TCSAASBOT/backend.out
```
**What it means**: Pages taking longer than 15 seconds to load
**Solution**: Either site is slow or blocking scrapers; may need to increase timeout

### Issue: Empty Sitemaps
**Look for**:
```bash
grep "urls_discovered" /Users/kamarajp/TCSAASBOT/backend.out | tail -1
```
**What it means**: Sitemap exists but found 0 URLs
**Solution**: Check sitemap XML format; may not be valid

## Test Scraping Dataflo.io

### Minimal Test (3 Pages, No Sitemaps)
```bash
curl -s -X POST "http://localhost:9100/api/v1/ingest/scrape" \
  -H "Content-Type: application/json" \
  -H "x-api-key: test-key" \
  -d '{
    "url": "https://www.dataflo.io/",
    "max_pages": 3,
    "use_sitemaps": false,
    "index_sections": true
  }'
```

### With Sitemaps (More Pages)
```bash
curl -s -X POST "http://localhost:9100/api/v1/ingest/scrape" \
  -H "Content-Type: application/json" \
  -H "x-api-key: test-key" \
  -d '{
    "url": "https://www.dataflo.io/",
    "max_pages": 50,
    "use_sitemaps": true,
    "index_sections": true
  }'
```

### Then Monitor Logs
```bash
# In another terminal, watch the scraping in real-time
tail -f /Users/kamarajp/TCSAASBOT/backend.out | \
  grep -E "scrape_request|sitemap|page_fetch|crawl_completed|ERROR"
```

## Performance Metrics

### Average Page Fetch Time
```bash
grep "page_fetch_complete" /Users/kamarajp/TCSAASBOT/backend.out | \
  jq '.extra.fetch_time_seconds' | \
  awk '{sum+=$1; count++} END {if (count > 0) print "Average: " sum/count " seconds"}'
```

### Slowest Pages (>5 seconds)
```bash
grep "page_fetch_complete" /Users/kamarajp/TCSAASBOT/backend.out | \
  jq 'select(.extra.fetch_time_seconds > 5) | .extra | {url, fetch_time_seconds}'
```

### Total Crawl Performance
```bash
grep "crawl_completed" /Users/kamarajp/TCSAASBOT/backend.out | tail -1 | \
  jq '.extra | {pages: .pages_scraped, time_seconds: .crawl_time_seconds, avg_ms: .average_page_time}'
```

## Troubleshooting Checklist

- [ ] Check scraper is running: `ps aux | grep uvicorn`
- [ ] Check backend logs exist: `ls -lh /Users/kamarajp/TCSAASBOT/backend.out`
- [ ] Tail logs in real-time: `tail -f backend.out`
- [ ] Check for robots.txt: `grep "robots" backend.out`
- [ ] Check for sitemaps: `grep "sitemap" backend.out | grep -i discovered`
- [ ] Check for HTTP errors: `grep "ERROR" backend.out | wc -l`
- [ ] Check 404s: `grep "page_fetch_http_error.*404" backend.out | wc -l`
- [ ] Check timeouts: `grep "timeout" backend.out | wc -l`
- [ ] View last request summary: `grep "scrape_request_completed" backend.out | tail -1`
- [ ] View last crawl stats: `grep "crawl_completed" backend.out | tail -1 | jq`

## Log File Locations

- **Backend Logs**: `/Users/kamarajp/TCSAASBOT/backend.out`
- **Dashboard Logs**: `/Users/kamarajp/TCSAASBOT/dashboard.out`
- **Mobile Logs**: `/Users/kamarajp/TCSAASBOT/mobile.out`

## Restart Backend to Apply Changes

```bash
cd /Users/kamarajp/TCSAASBOT
bash stop_all.sh
sleep 2
bash start_all.sh
```

## Related Documentation

- Main Implementation: `ENHANCED_SCRAPER_IMPLEMENTATION.md`
- Detailed Reference: `SCRAPER_LOGGING_ENHANCEMENT.md`
- OpenTelemetry Config: `backend/app/core/telemetry.py`
- Scraper Code: `backend/app/api/v1/ingest.py`
