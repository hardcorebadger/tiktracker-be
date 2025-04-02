#!/usr/bin/env python3

from playwright.async_api import async_playwright
import json
import time
import random
import re
import logging
import asyncio
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from dataclasses import dataclass
import aiohttp
import backoff

# Get logger without reconfiguring
logger = logging.getLogger(__name__)

@dataclass
class ProxyConfig:
    """Configuration for proxy settings"""
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None

    def get_proxy_url(self) -> str:
        """Generate proxy URL string"""
        auth = f"{self.username}:{self.password}@" if self.username and self.password else ""
        return f"http://{auth}{self.host}:{self.port}"

class RateLimiter:
    """Rate limiting implementation"""
    def __init__(self, requests_per_minute: int = 30):
        self.requests_per_minute = requests_per_minute
        self.requests = []
        
    async def wait_if_needed(self):
        """Wait if we've exceeded our rate limit"""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # Remove requests older than 1 minute
        self.requests = [req_time for req_time in self.requests if req_time > minute_ago]
        
        if len(self.requests) >= self.requests_per_minute:
            sleep_time = (self.requests[0] - minute_ago).total_seconds()
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            self.requests = self.requests[1:]
        
        self.requests.append(now)

@dataclass
class SoundMetadata:
    """Container for sound metadata"""
    video_count: Optional[int] = None
    sound_name: Optional[str] = None
    artist_name: Optional[str] = None

    def to_dict(self):
        return {
            "video_count": self.video_count,
            "sound_name": self.sound_name,
            "artist_name": self.artist_name
        }

class TikTokScraper:
    """
    A class to scrape video counts and other metrics from TikTok sound pages
    using Playwright for browser automation with anti-detection measures.
    """
    
    def __init__(self, proxy_list: Optional[List[ProxyConfig]] = None, requests_per_minute: int = 30):
        """
        Initialize the TikTok scraper with a Playwright browser instance.
        
        Args:
            proxy_list: List of proxy configurations to rotate through
            requests_per_minute: Maximum number of requests per minute
        """
        self.proxy_list = proxy_list or []
        self.current_proxy_index = 0
        self.rate_limiter = RateLimiter(requests_per_minute)
        self.results_cache = {}  # Simple cache for results
        self.playwright = None
        self.browser = None
        self.context = None
        
    async def setup_browser(self):
        """Initialize browser with current settings"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self._setup_stealth_context()
        logger.info("TikTok scraper initialized successfully")

    def _get_next_proxy(self) -> Optional[ProxyConfig]:
        """Rotate to next proxy in the list"""
        if not self.proxy_list:
            return None
        
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxy_list)
        return self.proxy_list[self.current_proxy_index]
        
    async def _setup_stealth_context(self):
        """
        Create a browser context with anti-detection measures.
        Returns:
            BrowserContext: A configured browser context with stealth measures
        """
        proxy = self._get_next_proxy()
        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "permissions": ["geolocation"],
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }
        }
        
        if proxy:
            context_options["proxy"] = {
                "server": proxy.get_proxy_url(),
                "username": proxy.username,
                "password": proxy.password
            }
            
        return await self.browser.new_context(**context_options)

    async def _add_human_behavior(self):
        """Simulate human-like delays between actions."""
        await asyncio.sleep(random.uniform(2, 4))

    @backoff.on_exception(
        backoff.expo,
        (Exception),
        max_tries=3,
        max_time=30
    )
    async def get_video_count(self, sound_url: str) -> Optional[int]:
        """
        Scrape the video count from a TikTok sound page with retry mechanism.
        
        Args:
            sound_url (str): The URL of the TikTok sound page
            
        Returns:
            int or None: The number of videos using the sound, or None if scraping fails
        """
        # Check cache first
        if sound_url in self.results_cache:
            return self.results_cache[sound_url]

        await self.rate_limiter.wait_if_needed()
        
        if not self.context:
            await self.setup_browser()
        
        page = None
        try:
            page = await self.context.new_page()
            logger.info(f"Navigating to {sound_url}")
            
            # Navigate to the page and wait for network to be idle
            await page.goto(sound_url, wait_until="networkidle")
            await self._add_human_behavior()
            
            # Try different selectors that might contain the video count
            selectors = [
                "text=videos",
                "[data-e2e='video-count']",
                ".video-count",
                "//span[contains(text(),'videos')]",  # XPath selector
                "//div[contains(@class,'video-count')]",  # Another XPath selector
                "//h3[contains(text(),'videos')]",  # Music page format
                "//h2[contains(text(),'videos')]",  # Alternative music page format
                "//div[contains(@class,'music-bar')]//span[contains(text(),'videos')]",  # Music bar specific
                "//div[contains(@class,'info-stats')]//strong[contains(text(),'videos')]",  # Stats section
                "//strong[contains(text(),'videos')]",  # Generic strong tag
                "//div[contains(@class,'stats')]//text()[contains(.,'videos')]"  # Any text containing videos
            ]
            
            for selector in selectors:
                try:
                    # Handle both CSS and XPath selectors
                    if selector.startswith("//"):
                        element = page.locator(f"xpath={selector}").first
                    else:
                        element = page.locator(selector).first
                        
                    if element:
                        video_count = await element.inner_text()
                        logger.debug(f"Found text with selector {selector}: {video_count}")
                        
                        def parse_count(count_str: str) -> Optional[int]:
                            """Parse count string with K/M suffixes"""
                            try:
                                # Remove any commas and whitespace
                                count_str = count_str.replace(',', '').strip()
                                
                                # Handle K/M suffixes
                                multiplier = 1
                                if 'K' in count_str.upper():
                                    multiplier = 1000
                                    count_str = count_str.upper().replace('K', '')
                                elif 'M' in count_str.upper():
                                    multiplier = 1000000
                                    count_str = count_str.upper().replace('M', '')
                                    
                                # Convert to float first to handle decimal points
                                base_count = float(count_str)
                                return int(base_count * multiplier)
                            except (ValueError, TypeError):
                                return None
                        
                        # Try different regex patterns
                        patterns = [
                            r'(\d+(?:\.\d+)?[KkMm]?)\s*videos?',  # 31M videos
                            r'(\d+(?:\.\d+)?[KkMm]?)\s*Videos?',  # 31M Videos
                            r'(\d+(?:,\d{3})*(?:\.\d+)?[KkMm]?)\s*videos?',  # 31,000,000 videos
                            r'(\d+(?:\.\d+)?)\s*[KkMm]\s*videos?',  # 31 M videos (space between number and suffix)
                            r'(\d+(?:,\d{3})*(?:\.\d+)?)',  # Just the number
                        ]
                        
                        for pattern in patterns:
                            count_match = re.search(pattern, video_count, re.IGNORECASE)
                            if count_match:
                                count_str = count_match.group(1)
                                count = parse_count(count_str)
                                if count is not None:
                                    logger.info(f"Successfully scraped video count: {count:,} (from {video_count})")
                                    self.results_cache[sound_url] = count
                                    return count
                                
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {str(e)}")
                    continue
            
            # If no count found, try to get page content for debugging
            try:
                content = await page.content()
                logger.debug(f"Page content: {content[:500]}...")  # First 500 chars for debugging
            except Exception as e:
                logger.debug(f"Could not get page content: {str(e)}")
            
            logger.warning("Could not find video count with any selector")
            return None
            
        except Exception as e:
            logger.error(f"Error scraping video count: {str(e)}")
            # If we get blocked, rotate proxy and retry
            if "blocked" in str(e).lower() or "denied" in str(e).lower():
                await self.rotate_proxy()
            return None
        finally:
            if page:
                await page.close()

    async def rotate_proxy(self):
        """Rotate to a new proxy and reinitialize the browser context"""
        logger.info("Rotating proxy and reinitializing browser context")
        await self.context.close()
        self.context = await self._setup_stealth_context()

    @backoff.on_exception(
        backoff.expo,
        (Exception),
        max_tries=3,
        max_time=30
    )
    async def get_sound_metadata(self, sound_url: str) -> SoundMetadata:
        """
        Scrape metadata from a TikTok sound page with retry mechanism.
        
        Args:
            sound_url (str): The URL of the TikTok sound page
            
        Returns:
            SoundMetadata: Object containing video count, sound name, and artist
        """
        # Check cache first
        if sound_url in self.results_cache:
            return self.results_cache[sound_url]

        await self.rate_limiter.wait_if_needed()
        
        if not self.context:
            await self.setup_browser()
        
        page = None
        try:
            page = await self.context.new_page()
            logger.info(f"Navigating to {sound_url}")
            
            # Navigate to the page and wait for network to be idle
            try:
                await page.goto(sound_url, wait_until="networkidle", timeout=10000)
            except Exception as e:
                logger.warning(f"Page load timeout, continuing anyway: {e}")
            
            await self._add_human_behavior()
            
            metadata = SoundMetadata()
            
            # Get video count first since we know this works
            metadata.video_count = await self._extract_video_count(page)
            
            async def try_selector(selector: str, timeout: int = 2000) -> Optional[str]:
                """Try to get text from a selector with timeout"""
                try:
                    element = page.locator(selector)
                    count = await element.count()
                    if count == 0:
                        return None
                        
                    try:
                        text = await element.first.text_content(timeout=timeout)
                        return text.strip() if text else None
                    except Exception as e:
                        logger.debug(f"Failed to get text content: {e}")
                        return None
                        
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {str(e)}")
                    return None
            
            # Try to get sound name from h1 with data-e2e="music-title"
            sound_name = await try_selector("[data-e2e='music-title']")
            if sound_name:
                metadata.sound_name = sound_name.strip()
                logger.debug(f"Found sound name: {sound_name}")
            
            # Try to get artist name from h2 with data-e2e="music-creator"
            artist_name = await try_selector("[data-e2e='music-creator']")
            if artist_name:
                metadata.artist_name = artist_name.strip()
                logger.debug(f"Found artist name: {artist_name}")
            
            # Cache the results even if some fields are missing
            self.results_cache[sound_url] = metadata
            return metadata
            
        except Exception as e:
            logger.error(f"Error scraping sound metadata: {str(e)}")
            if "blocked" in str(e).lower() or "denied" in str(e).lower():
                await self.rotate_proxy()
            return SoundMetadata(video_count=metadata.video_count if 'metadata' in locals() else None)
        finally:
            if page:
                await page.close()

    async def _extract_video_count(self, page) -> Optional[int]:
        """Extract video count from page using existing selectors and patterns"""
        try:
            # Try to get video count from h2 with data-e2e="music-video-count"
            element = page.locator("[data-e2e='music-video-count'] strong")
            count = await element.count()
            if count > 0:
                video_count = await element.first.text_content()
                logger.debug(f"Found video count text: {video_count}")
                
                def parse_count(count_str: str) -> Optional[int]:
                    """Parse count string with K/M suffixes"""
                    try:
                        # Remove any commas and whitespace
                        count_str = count_str.replace(',', '').strip()
                        
                        # Handle K/M suffixes
                        multiplier = 1
                        if 'K' in count_str.upper():
                            multiplier = 1000
                            count_str = count_str.upper().replace('K', '')
                        elif 'M' in count_str.upper():
                            multiplier = 1000000
                            count_str = count_str.upper().replace('M', '')
                            
                        # Convert to float first to handle decimal points
                        base_count = float(count_str)
                        return int(base_count * multiplier)
                    except (ValueError, TypeError):
                        return None
                
                # Try different regex patterns
                patterns = [
                    r'(\d+(?:\.\d+)?[KkMm]?)\s*videos?',  # 31M videos
                    r'(\d+(?:\.\d+)?[KkMm]?)\s*Videos?',  # 31M Videos
                    r'(\d+(?:,\d{3})*(?:\.\d+)?[KkMm]?)\s*videos?',  # 31,000,000 videos
                    r'(\d+(?:\.\d+)?)\s*[KkMm]\s*videos?',  # 31 M videos (space between number and suffix)
                    r'(\d+(?:,\d{3})*(?:\.\d+)?)',  # Just the number
                ]
                
                for pattern in patterns:
                    count_match = re.search(pattern, video_count, re.IGNORECASE)
                    if count_match:
                        count_str = count_match.group(1)
                        count = parse_count(count_str)
                        if count is not None:
                            logger.info(f"Successfully scraped video count: {count:,} (from {video_count})")
                            return count
                            
        except Exception as e:
            logger.debug(f"Failed to extract video count: {str(e)}")
        
        return None

    async def scrape_multiple_urls(self, urls: List[str], max_concurrent: int = 5) -> Dict[str, SoundMetadata]:
        """
        Scrape multiple URLs concurrently.
        
        Args:
            urls: List of TikTok sound URLs to scrape
            max_concurrent: Maximum number of concurrent scraping tasks
            
        Returns:
            Dict mapping URLs to their metadata
        """
        results = {}
        
        async def process_url(url: str):
            metadata = await self.get_sound_metadata(url)
            results[url] = metadata
        
        # Create tasks in batches to control concurrency
        for i in range(0, len(urls), max_concurrent):
            batch = urls[i:i + max_concurrent]
            batch_tasks = [process_url(url) for url in batch]
            await asyncio.gather(*batch_tasks)
            
        return results

    async def close(self):
        """Clean up browser resources."""
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("Browser resources cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

async def main():
    """Example usage of the TikTok scraper."""
    # Example proxy configuration
    proxy_list = [
        ProxyConfig(host="proxy1.example.com", port=8080),
        ProxyConfig(host="proxy2.example.com", port=8080),
        # Add more proxies as needed
    ]
    
    # Initialize scraper with proxy list and rate limiting
    scraper = TikTokScraper(proxy_list=proxy_list, requests_per_minute=30)
    
    try:
        # Single URL example
        url = "https://www.tiktok.com/t/ZT2T93YUy/"
        metadata = await scraper.get_sound_metadata(url)
        if metadata.video_count is not None:
            print(f"Video count: {metadata.video_count}")
            print(f"Sound name: {metadata.sound_name}")
            print(f"Artist name: {metadata.artist_name}")
        else:
            print("Failed to get video count")
            
        # Multiple URLs example
        urls = [
            "https://www.tiktok.com/t/example1/",
            "https://www.tiktok.com/t/example2/",
            "https://www.tiktok.com/t/example3/",
        ]
        
        results = await scraper.scrape_multiple_urls(urls, max_concurrent=3)
        
        # Print results
        for url, metadata in results.items():
            print(f"{url}: {metadata.video_count} videos, Sound: {metadata.sound_name}, Artist: {metadata.artist_name}")
            
    finally:
        await scraper.close()

if __name__ == "__main__":
    asyncio.run(main()) 