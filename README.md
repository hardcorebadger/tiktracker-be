# TikTok Sound Scraper Backend

A scalable system for scraping TikTok sound metadata using Modal for serverless execution and Supabase for data storage.

## Architecture Overview

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Supabase      │     │    Modal     │     │   Proxies    │     │    TikTok    │
│   (Data Store)  │◄────┤  (Scraper)   │────►│  (Optional)  │────►│    (Target)  │
└─────────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### Components

1. **Modal Functions**
   - `scrape_sound`: Scrapes a single TikTok sound URL
   - `process_sound_batch`: Handles concurrent scraping of multiple URLs
   - `scheduled_scraping`: Daily cron job for processing pending URLs

2. **Data Storage (Supabase)**
   - Stores scraping results and metadata
   - Tracks pending URLs and scraping history
   - Provides API for frontend access

3. **Proxy Management**
   - Rotating proxy support via Modal volume
   - Automatic proxy rotation on failures
   - Rate limiting per proxy

## Setup

1. **Install Dependencies**
   ```bash
   pip install modal-client supabase-py playwright
   ```

2. **Set up Modal**
   ```bash
   # Login to Modal
   modal token new

   # Create volume for proxy config
   modal volume create tiktok-scraper-volume
   ```

3. **Configure Supabase**
   ```sql
   -- Create the sounds table with user-specific tracking
   CREATE TABLE sounds (
       id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
       created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
       user_id UUID REFERENCES auth.users(id) NOT NULL,
       url TEXT NOT NULL,
       sound_name TEXT,
       creator_name TEXT,
       icon_url TEXT,
       video_count INTEGER DEFAULT 0,
       video_history INTEGER[] DEFAULT '{}',
       scrape_history TIMESTAMP WITH TIME ZONE[] DEFAULT '{}',
       last_scrape TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
       pct_change_1d DECIMAL DEFAULT 0,
       pct_change_1w DECIMAL DEFAULT 0,
       pct_change_1m DECIMAL DEFAULT 0,
       UNIQUE(user_id, url)  -- Ensure unique URLs per user
   );

   -- Create indexes for performance
   CREATE INDEX idx_sounds_user_url ON sounds(user_id, url);
   CREATE INDEX idx_sounds_last_scrape ON sounds(last_scrape);

   -- Enable Row Level Security (RLS)
   ALTER TABLE sounds ENABLE ROW LEVEL SECURITY;

   -- RLS Policies
   CREATE POLICY "Users can read their own sounds" ON sounds
       FOR SELECT TO authenticated USING (auth.uid() = user_id);

   CREATE POLICY "Users can insert their own sounds" ON sounds
       FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

   CREATE POLICY "Users can update their own sounds" ON sounds
       FOR UPDATE TO authenticated USING (auth.uid() = user_id)
       WITH CHECK (auth.uid() = user_id);

   CREATE POLICY "Users can delete their own sounds" ON sounds
       FOR DELETE TO authenticated USING (auth.uid() = user_id);
   ```

   Key features of the schema:
   - User-specific sound tracking
   - Historical video count tracking
   - Percentage change calculations
   - Row Level Security for data protection
   - Indexed fields for performance

4. **Set up Environment Variables**
   ```bash
   # Modal secrets
   modal secret create supabase-secrets SUPABASE_URL="your_url" SUPABASE_KEY="your_key"
   ```

## Proxy Setup and Management

### What are Proxies?
A proxy is like a middleman server that helps you access TikTok without revealing your real IP address. Think of it like using a different computer to access the internet.

### Why Do We Need Proxies?
- **Avoid Rate Limiting**: TikTok limits how many requests you can make from one IP address
- **Prevent Blocking**: If we make too many requests from one IP, TikTok might block us
- **Distribute Load**: We can spread our requests across multiple IPs to scrape more data

### How to Get Proxies
1. **Proxy Providers**:
   - [Bright Data](https://brightdata.com/) (formerly Luminati)
   - [Oxylabs](https://oxylabs.io/)
   - [SmartProxy](https://smartproxy.com/)
   - [IPRoyal](https://iproyal.com/)

2. **Types of Proxies**:
   - **Residential**: Real IPs from actual devices (most reliable, most expensive)
   - **Datacenter**: IPs from servers (cheaper, but more likely to be blocked)
   - **Rotating**: IPs that change automatically (good for avoiding blocks)

### Setting Up Proxies
```bash
# Create volume for proxy config
modal volume create tiktok-scraper-volume

# Update proxy list in Modal volume
modal volume put tiktok-scraper-volume proxies.json /root/data/proxies.json
```

Proxy Configuration (`proxies.json`):
```json
{
    "proxies": [
        {
            "host": "proxy1.example.com",
            "port": 8080,
            "username": "user1",
            "password": "pass1"
        }
    ]
}
```

- Local testing uses local `proxies.json`
- Modal deployment uses version in Modal volume
- Update Modal volume when proxy list changes

### Proxy Best Practices
- Start with 5-10 proxies for testing
- Monitor proxy success rates
- Rotate proxies when they fail
- Keep proxy credentials secure
- Use HTTPS proxies for better security

## Workflow

### 1. Core Files

```
backend/
├── sound_scraper_modal.py  # Main Modal deployment and cron job
├── tiktok_scraper.py       # Core scraping logic
└── scrape_example.py       # Local testing script
```

### 2. Deployment

```bash
# Test locally (without Modal)
python3 sound_scraper_modal.py

# Test on Modal infrastructure
modal run sound_scraper_modal.py

# Deploy the scheduled job to Modal (includes 5-minute cron schedule)
modal deploy sound_scraper_modal.py
```

### 3. Testing Options

1. **Local Testing** (No Modal)
   ```bash
   # Runs directly with Python, good for quick tests
   python3 sound_scraper_modal.py
   ```

2. **Modal Infrastructure Testing**
   ```bash
   # Tests on Modal's infrastructure but doesn't deploy
   modal run sound_scraper_modal.py
   ```

3. **Deployment Testing**
   ```bash
   # View Modal logs after deployment
   modal logs sound_scraper_modal.py

   # Check cron status
   modal cron list

   # View Modal dashboard
   modal dashboard
   ```

### 4. Automated Process

1. **Cron Job** (`sound_scraper_modal.py:modal_check_and_process_sounds`)
   - Runs every 5 minutes
   - Queries Supabase for sounds needing updates
   - Processes URLs in batches of 20 (configurable via BATCH_SIZE)

2. **Scraping Logic** (`tiktok_scraper.py`)
   - Handles browser automation
   - Extracts video count, sound name, artist
   - Manages rate limiting and proxies
   - Provides methods for single and batch URL processing

### 5. Data Flow

1. **Frontend → Supabase**
   - Users add URLs to track
   - Data stored in `sounds` table

2. **Modal → TikTok**
   - Scraper fetches current video counts
   - Handles rate limiting and proxies

3. **Modal → Supabase**
   - Updates video counts and history
   - Calculates percentage changes
   - Stores scraping timestamps

### 6. Monitoring

```bash
# View Modal logs
modal logs sound_scraper_modal.py

# Check cron status
modal cron list

# View Modal dashboard
modal dashboard
```

## Error Handling

1. **Scraping Errors**
   - Retries failed requests (max 3 times)
   - Exponential backoff
   - Error logging and tracking

2. **Proxy Errors**
   - Automatic proxy rotation
   - Proxy health monitoring
   - Fallback to direct connection

3. **Rate Limiting**
   - Respects TikTok's rate limits
   - Implements cooldown periods
   - Queue management

## Monitoring

1. **Modal Dashboard**
   - Function execution metrics
   - Error rates
   - Execution times

2. **Supabase Analytics**
   - Success/failure rates
   - Processing times
   - Queue status

## Usage Examples

### 1. Manual Scraping
```python
# Run batch scraping
results = process_sound_batch.remote([
    "https://www.tiktok.com/music/sound1",
    "https://www.tiktok.com/music/sound2"
])
```

### 2. Scheduled Scraping
```python
# Deploy scheduled job
modal deploy sound_scraper_modal.py
```

### 3. Query Results
```python
# Get recent results
storage = SupabaseStorage()
results = storage.get_results(limit=100)

# Get specific sound metadata
metadata = storage.get_sound_metadata("sound_url")
```

## Best Practices

1. **Rate Limiting**
   - Stay within TikTok's limits
   - Use appropriate batch sizes
   - Implement cooldown periods

2. **Proxy Usage**
   - Rotate proxies regularly
   - Monitor proxy health
   - Keep proxy list updated

3. **Error Handling**
   - Implement retries
   - Log errors properly
   - Monitor error rates

4. **Data Management**
   - Regular cleanup of old data
   - Monitor storage usage
   - Backup important data

## Troubleshooting

1. **Common Issues**
   - Proxy connection failures
   - Rate limiting
   - Browser automation errors

2. **Solutions**
   - Check proxy configuration
   - Adjust rate limits
   - Update Playwright
   - Check Modal logs

## Future Improvements

1. **Scalability**
   - Add more worker functions
   - Implement better queue management
   - Add more proxy providers

2. **Monitoring**
   - Add detailed metrics
   - Implement alerts
   - Better error tracking

3. **Features**
   - Add more metadata fields
   - Implement trend analysis
   - Add historical tracking 