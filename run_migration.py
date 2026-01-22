#!/usr/bin/env python3
"""
Run database migrations via Supabase
Uses the Supabase Python client to add columns
"""
import os
from supabase import create_client

# Get from Railway environment
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://owffvdmmvcnbnjaprqis.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im93ZmZ2ZG1tdmNuYm5qYXBycWlzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MDk4NTg4OSwiZXhwIjoyMDc2NTYxODg5fQ.0pt1sEoH8kCELmELgaEZJhrmneB80uPGgoQzzdTpB-M")

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
