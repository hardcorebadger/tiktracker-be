#!/usr/bin/env python3

import asyncio
import aiohttp
import time
from typing import List, Dict
from dataclasses import dataclass
import logging
from tiktok_scraper import ProxyConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_proxy(proxy: ProxyConfig) -> Dict:
    """Test a proxy configuration for speed and reliability"""
    start_time = time.time()
    result = {"proxy": proxy, "working": False, "speed": None, "error": None}
    
    try:
        proxy_url = proxy.get_proxy_url()
        async with aiohttp.ClientSession() as session:
            # Test with TikTok's domain
            async with session.get(
                "https://www.tiktok.com",
                proxy=proxy_url,
                timeout=10
            ) as response:
                if response.status == 200:
                    result["working"] = True
                    result["speed"] = time.time() - start_time
                else:
                    result["error"] = f"Status code: {response.status}"
    except Exception as e:
        result["error"] = str(e)
    
    return result

async def test_proxy_list(proxies: List[ProxyConfig]) -> List[Dict]:
    """Test multiple proxies concurrently"""
    tasks = [test_proxy(proxy) for proxy in proxies]
    return await asyncio.gather(*tasks)

def load_proxy_list(filename: str) -> List[ProxyConfig]:
    """Load proxy list from a file (format: host:port:username:password)"""
    proxies = []
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split(':')
            if len(parts) >= 2:
                proxy = ProxyConfig(
                    host=parts[0],
                    port=int(parts[1]),
                    username=parts[2] if len(parts) > 2 else None,
                    password=parts[3] if len(parts) > 3 else None
                )
                proxies.append(proxy)
    return proxies

def main():
    # Example proxies for testing
    test_proxies = [
        # Add your proxy configurations here
        ProxyConfig(host="proxy1.example.com", port=8080),
        ProxyConfig(host="proxy2.example.com", port=8080),
    ]
    
    # Or load from file
    # test_proxies = load_proxy_list('proxies.txt')
    
    results = asyncio.run(test_proxy_list(test_proxies))
    
    # Print results
    print("\nProxy Test Results:")
    print("-" * 50)
    for result in results:
        proxy = result["proxy"]
        if result["working"]:
            print(f"✅ {proxy.host}:{proxy.port} - {result['speed']:.2f}s")
        else:
            print(f"❌ {proxy.host}:{proxy.port} - Error: {result['error']}")

if __name__ == "__main__":
    main() 