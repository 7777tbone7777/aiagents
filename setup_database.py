#!/usr/bin/env python3
"""
Setup Supabase database for Bolt AI Group platform
Run this once to create all necessary tables
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")
    exit(1)

print("=" * 60)
print("BOLT AI GROUP - DATABASE SETUP")
print("=" * 60)

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# SQL schema
SCHEMA_SQL = """
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- BUSINESSES TABLE
CREATE TABLE IF NOT EXISTS businesses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMP DEFAULT NOW(),

    -- Business Info
    business_name TEXT NOT NULL,
    owner_name TEXT,
    owner_email TEXT,
    owner_phone TEXT,

    -- Industry & Configuration
    industry TEXT NOT NULL,
    agent_name TEXT DEFAULT 'Alex',

    -- AI Configuration
    custom_greeting TEXT,
    custom_prompt TEXT,
    capabilities JSONB DEFAULT '["appointments"]'::jsonb,

    -- Business Details
    business_hours JSONB,
    services JSONB,
    menu_url TEXT,

    -- Integration Settings
    google_calendar_id TEXT,
    google_calendar_credentials JSONB,

    -- Subscription
    plan TEXT DEFAULT 'starter',
    status TEXT DEFAULT 'active',
    monthly_rate DECIMAL(10,2) DEFAULT 99.00
);

-- PHONE_NUMBERS TABLE
CREATE TABLE IF NOT EXISTS phone_numbers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMP DEFAULT NOW(),

    business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,

    -- Twilio Info
    phone_number TEXT UNIQUE NOT NULL,
    twilio_sid TEXT,

    -- Configuration
    is_primary BOOLEAN DEFAULT true,
    purpose TEXT DEFAULT 'main'
);

-- CALLS TABLE
CREATE TABLE IF NOT EXISTS calls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMP DEFAULT NOW(),

    business_id UUID REFERENCES businesses(id),

    -- Call Info
    call_sid TEXT UNIQUE NOT NULL,
    from_number TEXT,
    to_number TEXT,
    direction TEXT,
    duration INTEGER,
    status TEXT,

    -- Lead Info
    caller_name TEXT,
    caller_email TEXT,

    -- Conversation
    transcript JSONB DEFAULT '[]'::jsonb,
    summary TEXT,
    disposition TEXT,

    -- Follow-up
    appointment_created BOOLEAN DEFAULT false,
    followup_sent BOOLEAN DEFAULT false
);

-- APPOINTMENTS TABLE
CREATE TABLE IF NOT EXISTS appointments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMP DEFAULT NOW(),

    business_id UUID REFERENCES businesses(id),
    call_id UUID REFERENCES calls(id),

    -- Appointment Details
    customer_name TEXT,
    customer_email TEXT,
    customer_phone TEXT,

    appointment_time TIMESTAMP NOT NULL,
    duration_minutes INTEGER DEFAULT 30,
    service_type TEXT,
    notes TEXT,

    -- Calendar Integration
    google_event_id TEXT,
    google_event_link TEXT,

    -- Status
    status TEXT DEFAULT 'scheduled',
    reminder_sent BOOLEAN DEFAULT false
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_calls_business ON calls(business_id);
CREATE INDEX IF NOT EXISTS idx_calls_created ON calls(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_appointments_business ON appointments(business_id);
CREATE INDEX IF NOT EXISTS idx_appointments_time ON appointments(appointment_time);
CREATE INDEX IF NOT EXISTS idx_phone_numbers ON phone_numbers(phone_number);
"""

print("\n📊 Creating database tables...")
print("\nNote: Supabase API doesn't support direct SQL execution.")
print("Please run this SQL manually in your Supabase dashboard:")
print("\n1. Go to: https://supabase.com/dashboard/project/[your-project]/sql")
print("2. Create a new query")
print("3. Paste and run the SQL below:")
print("\n" + "=" * 60)
print(SCHEMA_SQL)
print("=" * 60)

# Alternative: Insert a test business to verify connection
print("\n✅ Testing Supabase connection...")
try:
    # Try to query businesses table (will fail if doesn't exist)
    result = supabase.table('businesses').select("*").limit(1).execute()
    print(f"✓ Successfully connected! Found {len(result.data)} businesses.")
except Exception as e:
    print(f"⚠️  Tables don't exist yet. Please run the SQL above in Supabase dashboard.")
    print(f"   Error: {e}")

print("\n" + "=" * 60)
print("Next steps:")
print("1. Run the SQL in your Supabase dashboard")
print("2. Come back and run: python add_demo_business.py")
print("=" * 60)
