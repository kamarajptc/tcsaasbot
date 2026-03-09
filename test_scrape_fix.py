#!/usr/bin/env python3
"""Test the scraping fix for domain normalization issue"""

import requests
import json
import time

# Test scraping endpoint with Bearer token authentication
bearer_token = "test-token"

url = "http://localhost:9100/api/v1/ingest/scrape"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {bearer_token}"
}

payload = {
    "url": "https://www.dataflo.io/",
    "max_pages": 30,
    "use_sitemaps": True,
    "timeout": 60
}

print("=" * 60)
print("Testing Scraping with Domain Matching Fix")
print("=" * 60)
print(f"\nSending scraping request to: {payload['url']}")
print(f"Max pages: {payload['max_pages']}")
print(f"Using sitemaps: {payload['use_sitemaps']}\n")

start_time = time.time()
response = requests.post(url, json=payload, headers=headers, timeout=120)
elapsed = time.time() - start_time

print(f"Status Code: {response.status_code}")
print(f"Elapsed Time: {elapsed:.2f}s\n")

if response.status_code in [200, 202]:
    result = response.json()
    print("=" * 60)
    print("Scraping Results Summary")
    print("=" * 60)
    
    # Print key metrics
    for key in ['urls_discovered', 'successful_pages', 'failed_urls', 'http_errors', 'domain_mismatch_urls_skipped']:
        if key in result:
            value = result[key]
            if isinstance(value, list):
                print(f"{key}: {len(value)}")
            else:
                print(f"{key}: {value}")
    
    # Calculate success rate
    discovered = result.get('urls_discovered', 0)
    successful = result.get('successful_pages', 0)
    failed = result.get('failed_urls', 0)
    
    if discovered > 0:
        success_rate = (successful / discovered) * 100
        print(f"\n✓ Success Rate: {success_rate:.1f}% ({successful}/{discovered})")
    
    # Show sample of failed URLs if any
    failed_urls = result.get('failed_urls', [])
    if failed_urls:
        print(f"\nSample Failed URLs ({len(failed_urls)} total):")
        for url_info in failed_urls[:3]:
            if isinstance(url_info, dict):
                print(f"  - {url_info.get('url', url_info)} ({url_info.get('error', 'unknown error')})")
            else:
                print(f"  - {url_info}")
        if len(failed_urls) > 3:
            print(f"  ... and {len(failed_urls) - 3} more")
    
    # Show sample of successful pages
    successful_pages = result.get('successful_pages', [])
    if successful_pages:
        print(f"\nSample Successful Pages ({len(successful_pages)} total):")
        for page in successful_pages[:3]:
            if isinstance(page, dict):
                print(f"  - {page.get('url', page)}")
            else:
                print(f"  - {page}")
        if len(successful_pages) > 3:
            print(f"  ... and {len(successful_pages) - 3} more")
            
    print("\n" + "=" * 60)
    print("✅ Scraping Completed Successfully!")
    print("=" * 60)
    
else:
    print(f"❌ Error Response (Status {response.status_code}):")
    print(response.text[:1000])
