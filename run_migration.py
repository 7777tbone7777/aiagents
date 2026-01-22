#!/usr/bin/env python3
"""
Run database migrations via Supabase
Uses the Supabase Python client to add columns
"""
import os
from supabase import create_client

# Get from environment (no defaults - must be set)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables")
    exit(1)

print(f"Connecting to Supabase: {SUPABASE_URL[:40]}...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Test current schema by querying calls table
print("\nChecking current calls table schema...")
try:
    result = supabase.table('calls').select('*').limit(1).execute()
    if result.data:
        print(f"Current columns: {list(result.data[0].keys())}")

        # Check if recording columns exist
        has_recording = 'recording_url' in result.data[0]
        print(f"Has recording_url column: {has_recording}")
    else:
        print("No call records found, but table exists")
except Exception as e:
    print(f"Error querying calls table: {e}")

print("\n" + "="*60)
print("Migration SQL to run in Supabase Dashboard:")
print("="*60)
print("""
-- Run this SQL in: https://supabase.com/dashboard/project/owffvdmmvcnbnjaprqis/sql/new

-- Add recording columns to calls table
ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_url TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_sid TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_duration INTEGER;

-- Verify
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'calls';
""")
print("="*60)
