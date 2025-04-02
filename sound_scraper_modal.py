import modal
import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
from supabase_storage import SupabaseStorage
import logging
from tiktok_scraper import TikTokScraper

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
BATCH_SIZE = 20  # Number of sounds to process in each batch
UPDATE_INTERVAL = timedelta(hours=24)  # How often to update each sound
CHECK_INTERVAL = timedelta(minutes=5)  # How often to check for sounds needing updates

# Define the Modal app
app = modal.App("sound-tracker")

# Create a Modal image with our dependencies
image = modal.Image.debian_slim().pip_install(
    "playwright",
    "aiohttp",
    "backoff",
    "supabase-py",
    "python-dotenv",
).run_commands("playwright install chromium")

# Add local modules to the image
image = image.add_local_python_source("supabase_storage", "tiktok_scraper")

def get_modal_secret():
    """Get Supabase credentials from Modal secret or environment variables"""
    try:
        secret = modal.Secret.from_name("supabase-secrets")
        return secret["SUPABASE_URL"], secret["SUPABASE_KEY"]
    except Exception:
        return os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")

async def process_sound_batch(urls: List[str]):
    """Process a batch of sound URLs"""
    supabase_url, supabase_key = get_modal_secret()
    storage = SupabaseStorage(supabase_url, supabase_key)
    
    try:
        # Initialize scraper with rate limiting
        scraper = TikTokScraper(requests_per_minute=30)
        await scraper.setup_browser()
        
        # Scrape URLs in parallel with rate limiting
        results = await scraper.scrape_multiple_urls(urls, max_concurrent=5)
        
        # Prepare metadata for batch update
        url_to_metadata = {}
        for url, metadata in results.items():
            if metadata.video_count is not None:
                url_to_metadata[url] = {
                    "video_count": metadata.video_count,
                    "sound_name": metadata.sound_name,
                    "artist_name": metadata.artist_name,
                    "total_views": 0,  # We'll add this later if needed
                    "icon_url": None   # We'll add this later if needed
                }
        
        # Batch update results in Supabase
        if url_to_metadata:
            success = storage.batch_update_sounds(url_to_metadata)
            if success:
                logger.info(f"Successfully updated {len(url_to_metadata)} sounds")
            else:
                logger.error("Failed to update sounds")
                
    except Exception as e:
        logger.error(f"Error processing batch: {e}")
    finally:
        await scraper.close()

async def check_and_process_sounds():
    """Check for sounds needing updates and process them"""
    supabase_url, supabase_key = get_modal_secret()
    storage = SupabaseStorage(supabase_url, supabase_key)
    
    try:
        # Get sounds that need updating, prioritizing:
        # 1. New sounds (null last_scrape)
        # 2. Sounds not updated in the last 24 hours
        cutoff = (datetime.now() - UPDATE_INTERVAL).isoformat()
        response = storage.client.table("sounds") \
            .select("url") \
            .or_(f"last_scrape.is.null,last_scrape.lt.{cutoff}") \
            .order("last_scrape", nullsfirst=True) \
            .limit(BATCH_SIZE) \
            .execute()
        
        sounds = response.data
        if not sounds:
            logger.info("No sounds need updating")
            return
            
        # Extract unique URLs
        urls = [sound["url"] for sound in sounds]
        logger.info(f"Processing {len(urls)} sounds that need updating")
        
        # Process the batch
        await process_sound_batch(urls)
        
    except Exception as e:
        logger.error(f"Error in check_and_process_sounds: {e}")

# Modal version of the job
@app.function(
    image=image,
    secrets=[modal.Secret.from_name("supabase-secrets")],
    timeout=3600,
    schedule=modal.Period(minutes=5),  # Check every 5 minutes
)
async def modal_check_and_process_sounds():
    """Modal version of the main job"""
    await check_and_process_sounds()

@app.local_entrypoint()
async def main():
    """Run the main job locally"""
    await check_and_process_sounds()

if __name__ == "__main__":
    # Run the job locally
    asyncio.run(check_and_process_sounds()) 