#!/usr/bin/env python3
"""Test domain auto-correction feature"""
import sys
sys.path.insert(0, '/Users/kamarajp/TCSAASBOT/backend')

from app.core.security import create_access_token
import requests
import time

token = create_access_token({"sub": "test-domain-correction", "tenant_id": "test-domain-correction"})

url = "http://localhost:9100/api/v1/ingest/scrape"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

# Test with WRONG domain variant (non-www)
payload = {
    "url": "https://dataflo.io/",  # Non-www (wrong variant)
    "max_pages": 10,
    "use_sitemaps": True,
    "timeout": 60
}

print("=" * 70)
print("Testing Domain Auto-Correction")
print("=" * 70)
print(f"\nInput: {payload['url']} (non-www, likely incorrect)")
print("Expected: System auto-detects www.dataflo.io, corrects domain\n")

start_time = time.time()
response = requests.post(url, json=payload, headers=headers, timeout=120)
elapsed = time.time() - start_time

print(f"Response Time: {elapsed:.1f}s")
print(f"Status Code: {response.status_code}\n")

if response.status_code == 200:
    result = response.json()
    
    print("=" * 70)
    print("Results")
    print("=" * 70)
    
    pages_scraped = result.get('pages_scraped', 0)
    pages_discovered = result.get('pages_discovered', 0)
    
    print(f"\nPages Scraped: {pages_scraped}")
    print(f"Pages Discovered: {pages_discovered}")
    print(f"Failed Pages: {result.get('failed_pages', 0)}")
    print(f"New Pages Indexed: {result.get('new_pages_indexed', 0)}")
    
    if pages_scraped > 0:
        success_rate = (pages_scraped / pages_discovered * 100) if pages_discovered > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        
    if pages_scraped > 5:
        print("\n✅ AUTO-CORRECTION WORKING!")
        print("   System successfully auto-corrected to www.dataflo.io")
    else:
        print("\n⚠️  Low success - check backend logs")
    
    print("\n" + "=" * 70)
    
else:
    print(f"Error: {response.status_code}")
    print(response.text[:500])
