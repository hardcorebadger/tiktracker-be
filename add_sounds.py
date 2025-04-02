import os
from dotenv import load_dotenv
from supabase_storage import SupabaseStorage
from datetime import datetime
import json

# Load environment variables
load_dotenv()

def add_sounds(user_id: str, urls: list[str]):
    """Add new sound URLs to Supabase for a user"""
    storage = SupabaseStorage()
    
    # Convert URLs to initial sound records
    sounds = []
    for url in urls:
        sound = {
            "user_id": user_id,
            "url": url,
            "created_at": datetime.now().isoformat(),
            "last_scrape": None,
            "video_count": None,
            "video_history": [],
            "scrape_history": [],
            "pct_change_1d": None,
            "pct_change_1w": None,
            "pct_change_1m": None
        }
        sounds.append(sound)
    
    # Add sounds to Supabase
    try:
        storage.client.table("sounds").insert(sounds).execute()
        print(f"Successfully added {len(sounds)} sounds for user {user_id}")
    except Exception as e:
        print(f"Error adding sounds: {e}")

def main():
    # Example usage
    test_user_id = "75feb40f-de91-4580-b9b3-33b393b54491"  # Replace with actual user ID
    
    # Example URLs to add
    urls = [
        "https://www.tiktok.com/t/ZT2T93YUy/",
        "https://www.tiktok.com/t/ZT2TxH36P/",
        "https://www.tiktok.com/t/ZT2TxEnQG/"
    ]
    
    add_sounds(test_user_id, urls)

if __name__ == "__main__":
    main() 