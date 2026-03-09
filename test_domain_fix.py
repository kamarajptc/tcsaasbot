#!/usr/bin/env python3
"""Test the scraping fix for domain normalization issue"""
import sys
sys.path.insert(0, '/Users/kamarajp/TCSAASBOT/backend')

from app.core.security import create_access_token
import requests
import time

# Create JWT token
token = create_access_token({"sub": "test-tenant", "tenant_id": "test-tenant"})
print(f"✓ Generated JWT Token\n")

# Prepare request
url = "http://localhost:9100/api/v1/ingest/scrape"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

payload = {
    "url": "https://www.dataflo.io/",
    "max_pages": 20,
    "use_sitemaps": True,
    "timeout": 60
}

print("=" * 70)
print("Testing Domain Matching Fix for dataflo.io Scraping")
print("=" * 70)
print(f"\nEndpoint: POST /api/v1/ingest/scrape")
print(f"Target: {payload['url']}")
print(f"Max Pages: {payload['max_pages']}")
print(f"Use Sitemaps: {payload['use_sitemaps']}\n")

print("Sending request... (this may take a minute)")
start_time = time.time()

try:
    response = requests.post(url, json=payload, headers=headers, timeout=120)
    elapsed = time.time() - start_time
    
    print(f"Response received in {elapsed:.1f}s\n")
    print(f"Status Code: {response.status_code}\n")
    
    if response.status_code == 200:
        result = response.json()
        
        print("=" * 70)
        print("Scraping Results")
        print("=" * 70)
        
        # Key metrics
        urls_discovered = result.get('urls_discovered', 0)
        successful = result.get('successful_pages', 0)
        failed = result.get('failed_urls', 0)
        domain_mismatches = result.get('domain_mismatch_urls_skipped', 0)
        
        print(f"\nURLs Discovered: {urls_discovered}")
        print(f"Successful Pages: {successful}")
        print(f"Failed URLs: {len(failed) if isinstance(failed, list) else failed}")
        print(f"Domain Mismatches Skipped: {domain_mismatches}")
        
        # Calculate success rate
        if urls_discovered > 0:
            success_rate = (successful / urls_discovered) * 100
            print(f"\nSuccess Rate: {success_rate:.1f}%")
            
        # Before fix: ~738 discovered, ~723 failed, ~2% success
        # After fix: should have much fewer discovered (domain mismatch filtering)
        # and much higher success rate on valid domain
        print("\n" + "=" * 70)
        print("Analysis vs Previous Run")
        print("=" * 70)
        print("\nBefore fix:")
        print("  - URLs Discovered: ~738")
        print("  - Failed: ~723")
        print("  - Success Rate: ~2%")
        print("  - Cause: Domain variant mixing (www vs non-www)")
        
        print("\nAfter fix (current run):")
        print(f"  - URLs Discovered: {urls_discovered}")
        print(f"  - Failed: {len(failed) if isinstance(failed, list) else failed}")
        if urls_discovered > 0:
            print(f"  - Success Rate: {success_rate:.1f}%")
        print(f"  - Domain Mismatches Skipped: {domain_mismatches}")
        
        if domain_mismatches > 0:
            print("\nFIX WORKING: Domain mismatches are being filtered!")
        
        if urls_discovered > 0 and success_rate > 80:
            print("FIX EFFECTIVE: Success rate improved significantly!")
        
        # Show sample errors if any
        if isinstance(failed, list) and failed:
            print(f"\nSample Failed URLs ({len(failed)} total):")
            for item in failed[:3]:
                if isinstance(item, dict):
                    print(f"  - {item.get('url', '?')}")
                else:
                    print(f"  - {item}")
            if len(failed) > 3:
                print(f"  ... and {len(failed) - 3} more")
        
        print("\n" + "=" * 70)
        
    else:
        print(f"Error: {response.status_code}")
        print(response.text[:500])
        
except Exception as e:
    print(f"Request failed: {e}")
    import traceback
    traceback.print_exc()
