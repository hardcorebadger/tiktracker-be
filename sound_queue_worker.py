#!/usr/bin/env python3

from celery import Celery
import asyncio
from tiktok_scraper import TikTokScraper, ProxyConfig, SoundMetadata
import json
from datetime import datetime
import logging
from typing import List, Dict
import os
import sys
from redis import Redis
import backoff

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('sound_scraper.log')
    ]
)
logger = logging.getLogger(__name__)

# Initialize Celery with Redis backend
app = Celery('sound_scraper',
             broker='redis://localhost:6379/0',
             backend='redis://localhost:6379/0')

# Configure Celery
app.conf.update(
    worker_prefetch_multiplier=1,  # One task per worker at a time
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks
    task_time_limit=300,  # 5 minute timeout per task
    task_soft_time_limit=240,  # Soft timeout 4 minutes
    task_routes={
        'sound_queue_worker.scrape_sound': {'queue': 'sound_scraping'}
    }
)

# Redis client for rate limiting
redis_client = Redis(host='localhost', port=6379, db=1)

class ProxyManager:
    def __init__(self, proxy_file: str = 'proxies.json'):
        self.proxy_file = proxy_file
        self.proxies: List[ProxyConfig] = []
        self.load_proxies()
    
    def load_proxies(self):
        """Load proxies from JSON file"""
        try:
            with open(self.proxy_file, 'r') as f:
                proxy_data = json.load(f)
                self.proxies = [
                    ProxyConfig(
                        host=p['host'],
                        port=p['port'],
                        username=p.get('username'),
                        password=p.get('password')
                    ) for p in proxy_data
                ]
            logger.info(f"Loaded {len(self.proxies)} proxies")
        except Exception as e:
            logger.error(f"Failed to load proxies: {e}")
            self.proxies = []

    def get_proxy_list(self, count: int = 5) -> List[ProxyConfig]:
        """Get a subset of proxies to use"""
        if not self.proxies:
            return []
        # Rotate through proxies
        return self.proxies[:count]

class ResultsManager:
    def __init__(self, output_dir: str = 'results'):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def save_results(self, url: str, metadata: Dict):
        """Save results to JSON file"""
        timestamp = datetime.now().strftime('%Y%m%d')
        filename = f"{self.output_dir}/results_{timestamp}.json"
        
        try:
            # Load existing results
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    results = json.load(f)
            else:
                results = {}
            
            # Add new result
            results[url] = {
                'metadata': metadata,
                'timestamp': datetime.now().isoformat()
            }
            
            # Save updated results
            with open(filename, 'w') as f:
                json.dump(results, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save results for {url}: {e}")

proxy_manager = ProxyManager()
results_manager = ResultsManager()

@app.task(bind=True, max_retries=3)
def scrape_sound(self, sound_url: str) -> Dict:
    """Celery task to scrape a single sound URL"""
    try:
        # Rate limiting using Redis
        key = f"ratelimit:{sound_url.split('/')[-1]}"
        if redis_client.get(key):
            # Requeue if we're rate limited
            self.retry(countdown=60)
            return None
            
        # Set rate limit
        redis_client.setex(key, 60, 1)  # 1 minute cooldown per URL
        
        # Get proxy list
        proxy_list = proxy_manager.get_proxy_list()
        
        # Run the async scraper
        scraper = TikTokScraper(
            proxy_list=proxy_list,
            requests_per_minute=30
        )
        
        # Run in event loop
        loop = asyncio.get_event_loop()
        metadata = loop.run_until_complete(scrape_single_url(scraper, sound_url))
        
        # Save results
        if metadata:
            results_manager.save_results(sound_url, metadata.to_dict())
            return metadata.to_dict()
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to scrape {sound_url}: {e}")
        # Retry with exponential backoff
        self.retry(exc=e, countdown=backoff.expo(self.request.retries, base=60))

async def scrape_single_url(scraper: TikTokScraper, url: str) -> SoundMetadata:
    """Helper function to run async scraper"""
    try:
        metadata = await scraper.get_sound_metadata(url)
        await scraper.close()
        return metadata
    except Exception as e:
        logger.error(f"Error in scrape_single_url: {e}")
        await scraper.close()
        return None

if __name__ == '__main__':
    # Start Celery worker
    app.worker_main(['worker', '--loglevel=INFO', '-Q', 'sound_scraping']) 