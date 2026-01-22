#!/usr/bin/env python3
"""
Add recording columns to calls table via Supabase
This uses a workaround - we try to update a record with the new columns,
which will fail if they don't exist, then we know we need manual migration.
"""
import os
from supabase import create_client

SUPABASE_URL = "https://owffvdmmvcnbnjaprqis.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im93ZmZ2ZG1tdmNuYm5qYXBycWlzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MDk4NTg4OSwiZXhwIjoyMDc2NTYxODg5fQ.0pt1sEoH8kCELmELgaEZJhrmneB80uPGgoQzzdTpB-M"

print("Connecting to Supabase...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Check if columns exist by querying a call
print("\nChecking current schema...")
try:
    result = supabase.table('calls').select('*').limit(1).execute()
    if result.data:
        columns = list(result.data[0].keys())
        print(f"Current columns: {columns}")

        has_recording_url = 'recording_url' in columns
        has_recording_sid = 'recording_sid' in columns
        has_recording_duration = 'recording_duration' in columns

        print(f"\nrecording_url exists: {has_recording_url}")
        print(f"recording_sid exists: {has_recording_sid}")
        print(f"recording_duration exists: {has_recording_duration}")

        if has_recording_url and has_recording_sid and has_recording_duration:
            print("\n✅ All recording columns already exist!")
        else:
            print("\n⚠️  Missing columns. Please run this SQL in Supabase Dashboard:")
            print("   https://supabase.com/dashboard/project/owffvdmmvcnbnjaprqis/sql/new")
            print("\n   ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_url TEXT;")
            print("   ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_sid TEXT;")
            print("   ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_duration INTEGER;")
    else:
        print("No calls found in database, but table exists")
        print("Columns cannot be verified without data")
        print("\nPlease ensure these columns exist by running in Supabase Dashboard:")
        print("   https://supabase.com/dashboard/project/owffvdmmvcnbnjaprqis/sql/new")
        print("\n   ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_url TEXT;")
        print("   ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_sid TEXT;")
        print("   ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_duration INTEGER;")

except Exception as e:
    print(f"Error: {e}")
