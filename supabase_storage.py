from supabase import create_client, Client
import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import uuid
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

class SupabaseStorage:
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        """Initialize Supabase client with URL and key"""
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("Supabase URL and key must be provided either as arguments or environment variables")
            
        self.client: Client = create_client(self.url, self.key)
        
    def _calculate_percentage_changes(self, video_history: List[Dict]) -> Dict[str, float]:
        """Calculate percentage changes in video count over different time periods"""
        if not video_history:
            return {"1d": None, "1w": None, "1m": None}
            
        # Sort history by timestamp
        sorted_history = sorted(video_history, key=lambda x: x["timestamp"])
        latest_count = sorted_history[-1]["count"]
        latest_time = datetime.fromisoformat(sorted_history[-1]["timestamp"].replace('Z', '+00:00'))
        
        def get_previous_count(hours: int) -> Optional[int]:
            """Get count from specified hours ago"""
            cutoff = latest_time - timedelta(hours=hours)
            
            for entry in reversed(sorted_history[:-1]):
                entry_time = datetime.fromisoformat(entry["timestamp"].replace('Z', '+00:00'))
                if entry_time <= cutoff:
                    return entry["count"]
            return None
        
        # Calculate changes
        changes = {}
        for period, hours in [("1d", 24), ("1w", 168), ("1m", 720)]:
            prev_count = get_previous_count(hours)
            if prev_count and prev_count > 0:
                changes[period] = ((latest_count - prev_count) / prev_count) * 100
            else:
                changes[period] = None
                
        return changes
        
    def get_sound_by_url(self, url: str) -> Optional[Dict]:
        """Get a specific sound by URL"""
        try:
            response = self.client.table("sounds") \
                .select("*") \
                .eq("url", url) \
                .limit(1) \
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error getting sound by URL: {e}")
            return None
            
    def batch_update_sounds(self, url_to_metadata: Dict[str, Dict]) -> bool:
        """
        Efficiently update multiple sounds at once.
        
        Args:
            url_to_metadata: Dictionary mapping URLs to their metadata
        """
        try:
            now = datetime.now().astimezone()  # Make timezone-aware
            updates = []
            inserts = []
            
            for url, metadata in url_to_metadata.items():
                # Get existing sound
                existing = self.get_sound_by_url(url)
                
                if existing:
                    # Update existing record
                    try:
                        video_history = existing.get("video_history", [])
                        scrape_history = existing.get("scrape_history", [])
                        # Ensure scrape_history timestamps are timezone-aware
                        scrape_history = [ts if '+' in ts or 'Z' in ts else ts + '+00:00' for ts in scrape_history]
                    except (TypeError, AttributeError):
                        # If array access fails, start fresh
                        video_history = []
                        scrape_history = []
                    
                    if metadata.get("video_count") is not None:
                        video_history.append(metadata["video_count"])
                    
                    scrape_history.append(now.isoformat())
                    
                    pct_changes = self._calculate_percentage_changes([
                        {"timestamp": ts, "count": count}
                        for ts, count in zip(scrape_history, video_history)
                    ])
                    
                    updates.append({
                        "url": url,
                        "video_count": metadata.get("video_count"),
                        "video_history": video_history,
                        "scrape_history": scrape_history,
                        "last_scrape": now.isoformat(),
                        "sound_name": metadata.get("sound_name"),
                        "creator_name": metadata.get("artist_name"),
                        "icon_url": metadata.get("icon_url"),
                        "pct_change_1d": pct_changes["1d"],
                        "pct_change_1w": pct_changes["1w"],
                        "pct_change_1m": pct_changes["1m"]
                    })
                else:
                    # Create new record
                    initial_video_history = [metadata.get("video_count")] if metadata.get("video_count") is not None else []
                    initial_scrape_history = [now.isoformat()]
                    
                    inserts.append({
                        "id": str(uuid.uuid4()),
                        "created_at": now.isoformat(),
                        "url": url,
                        "sound_name": metadata.get("sound_name"),
                        "creator_name": metadata.get("artist_name"),
                        "icon_url": metadata.get("icon_url"),
                        "video_count": metadata.get("video_count"),
                        "video_history": initial_video_history,
                        "scrape_history": initial_scrape_history,
                        "last_scrape": now.isoformat(),
                        "pct_change_1d": None,
                        "pct_change_1w": None,
                        "pct_change_1m": None
                    })
            
            # Perform batch operations
            if updates:
                for update in updates:
                    self.client.table("sounds") \
                        .update(update) \
                        .eq("url", update["url"]) \
                        .execute()
                        
            if inserts:
                self.client.table("sounds").insert(inserts).execute()
                
            return True
        except Exception as e:
            print(f"Failed to batch update sounds: {e}")
            return False 