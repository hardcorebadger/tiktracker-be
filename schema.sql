-- Create the sounds table
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

-- Create indexes
CREATE INDEX idx_sounds_user_url ON sounds(user_id, url);
CREATE INDEX idx_sounds_last_scrape ON sounds(last_scrape);

-- Enable RLS
ALTER TABLE sounds ENABLE ROW LEVEL SECURITY;

-- Allow users to read their own sounds
CREATE POLICY "Users can read their own sounds" ON sounds
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

-- Allow users to insert their own sounds
CREATE POLICY "Users can insert their own sounds" ON sounds
    FOR INSERT
    TO authenticated
    WITH CHECK (auth.uid() = user_id);

-- Allow users to update their own sounds
CREATE POLICY "Users can update their own sounds" ON sounds
    FOR UPDATE
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id); 

-- Allow users to delete their own sounds
CREATE POLICY "Users can delete their own sounds" ON sounds
    FOR DELETE
    TO authenticated
    USING (auth.uid() = user_id);

-- Create subscriptions table
create table subscriptions (
  id uuid default uuid_generate_v4() primary key,
  user_id uuid references auth.users not null,
  stripe_customer_id text,
  stripe_subscription_id text,
  status text check (status in ('active', 'canceled', 'past_due')),
  current_period_end timestamp with time zone,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- Add RLS policies
alter table subscriptions enable row level security;

-- Users can read their own subscription
create policy "Users can view own subscription"
  on subscriptions for select
  using (auth.uid() = user_id);

-- Only service role can insert/update/delete
create policy "Service role can manage subscriptions"
  on subscriptions for all
  using (auth.role() = 'service_role');