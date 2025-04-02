#!/usr/bin/env python3

import asyncio
from tiktok_scraper import TikTokScraper, ProxyConfig
import logging
import json
from typing import List, Dict
from datetime import datetime

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,  # Change to DEBUG for more detailed logs
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def save_results(results: Dict[str, dict], filename: str = None):
    """Save scraping results to a JSON file"""
    if filename is None:
        filename = f"tiktok_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    # Convert results to dictionary format
    results_dict = {url: metadata.to_dict() for url, metadata in results.items()}
    
    with open(filename, 'w') as f:
        json.dump(results_dict, f, indent=2)
    logger.info(f"Results saved to {filename}")

async def main():
    # Example 1: Simple usage without proxies
    logger.info("Testing scraper without proxies...")
    scraper = TikTokScraper(requests_per_minute=30)
    
    # Test URLs with different formats
    test_urls = [
        # Music page formats
        "https://www.tiktok.com/music/Love-You-So-6728562975734515713",
        # Sound page formats
        "https://www.tiktok.com/t/ZT2T93YUy/",
        "https://www.tiktok.com/t/ZT2TxH36P/",
        "https://www.tiktok.com/t/ZT2TxEnQG/"
    ]
    
    try:
        # Test each URL format individually
        for url in test_urls:
            logger.info(f"\nTesting URL: {url}")
            metadata = await scraper.get_sound_metadata(url)
            print(f"\nResults for {url}:")
            print(f"Video count: {metadata.video_count:,}" if metadata.video_count else "Video count: Not found")
            print(f"Sound name: {metadata.sound_name or 'Not found'}")
            print(f"Artist name: {metadata.artist_name or 'Not found'}")
            
        # Test concurrent scraping
        logger.info("\nTesting concurrent scraping...")
        results = await scraper.scrape_multiple_urls(test_urls, max_concurrent=2)
        
        print("\nAll results:")
        for url, metadata in results.items():
            print(f"\n{url}:")
            print(f"Video count: {metadata.video_count:,}" if metadata.video_count else "Video count: Not found")
            print(f"Sound name: {metadata.sound_name or 'Not found'}")
            print(f"Artist name: {metadata.artist_name or 'Not found'}")
            
        # Save results
        await save_results(results)
        
    finally:
        await scraper.close()
    
    # Example 2: Usage with proxies (commented out - uncomment when you have proxies)
    """
    # Load proxies from your proxy provider
    proxy_list = [
        ProxyConfig(
            host="pr.oxylabs.io",  # Replace with your proxy host
            port=7777,             # Replace with your proxy port
            username="your-user",  # Replace with your username
            password="your-pass"   # Replace with your password
        ),
        # Add more proxies as needed
    ]
    
    scraper_with_proxies = TikTokScraper(
        proxy_list=proxy_list,
        requests_per_minute=30
    )
    
    try:
        results = await scraper_with_proxies.scrape_multiple_urls(
            test_urls,
            max_concurrent=3
        )
        save_results(results, "proxy_results.json")
    finally:
        scraper_with_proxies.close()
    """

if __name__ == "__main__":
    asyncio.run(main()) 