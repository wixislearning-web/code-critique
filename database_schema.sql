-- CodeCritique Database Schema
-- Run this SQL in your Supabase SQL Editor

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    github_id TEXT UNIQUE NOT NULL,
    github_username TEXT NOT NULL,
    github_access_token TEXT NOT NULL,
    email TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Reviews table
CREATE TABLE IF NOT EXISTS reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    repo_name TEXT NOT NULL,
    repo_full_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    context TEXT,
    focus_areas TEXT[],
    feedback JSONB,
    scores JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Subscriptions table
CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tier TEXT NOT NULL DEFAULT 'free',
    reviews_used_this_month INTEGER DEFAULT 0,
    reviews_limit INTEGER DEFAULT 2,
    subscription_start TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    subscription_end TIMESTAMP WITH TIME ZONE,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_reviews_user_id ON reviews(user_id);
CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);
CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_users_github_id ON users(github_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);

-- Enable Row Level Security (RLS)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

-- RLS Policies - Allow service role to bypass RLS
-- This allows the backend to access all data using the service role key
CREATE POLICY "Enable all access for service role" ON users 
    FOR ALL 
    USING (true);

CREATE POLICY "Enable all access for service role" ON reviews 
    FOR ALL 
    USING (true);

CREATE POLICY "Enable all access for service role" ON subscriptions 
    FOR ALL 
    USING (true);

-- Optional: Add comments
COMMENT ON TABLE users IS 'CodeCritique users authenticated via GitHub OAuth';
COMMENT ON TABLE reviews IS 'Code review requests and results';
COMMENT ON TABLE subscriptions IS 'User subscription tiers and limits';