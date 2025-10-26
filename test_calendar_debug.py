#!/usr/bin/env python3
"""Debug calendar integration"""
import os, json, sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("CALENDAR INTEGRATION DEBUG")
print("=" * 60)

# 1. Check environment
print("\n1. Environment Variables:")
print(f"   GOOGLE_SERVICE_ACCOUNT_FILE: {os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')}")
print(f"   GOOGLE_CALENDAR_ID: {os.getenv('GOOGLE_CALENDAR_ID', 'primary')}")

# 2. Check service account file
sa_file = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
if not sa_file or not os.path.exists(sa_file):
    print(f"\n   ❌ Service account file not found: {sa_file}")
    sys.exit(1)

with open(sa_file) as f:
    sa_data = json.load(f)
    print(f"\n   Service Account Email: {sa_data.get('client_email')}")

# 3. Try to initialize calendar service
print("\n2. Initializing Calendar Service...")
try:
    from googleapiclient.discovery import build
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/calendar"]
    creds = Credentials.from_service_account_file(sa_file, scopes=scopes)
    service = build('calendar', 'v3', credentials=creds)
    print("   ✓ Calendar service initialized successfully!")

    # 4. Try to list calendars
    print("\n3. Testing Calendar Access...")
    try:
        calendars = service.calendarList().list().execute()
        print(f"   ✓ Found {len(calendars.get('items', []))} calendars:")
        for cal in calendars.get('items', []):
            print(f"     - {cal.get('summary')} (ID: {cal.get('id')})")
    except Exception as e:
        print(f"   ❌ Cannot list calendars: {e}")
        print("\n   LIKELY ISSUE: Service account doesn't have calendar access!")
        print(f"\n   TO FIX:")
        print(f"   1. Go to https://calendar.google.com")
        print(f"   2. Settings → Add people → {sa_data.get('client_email')}")
        print(f"   3. Give 'Make changes to events' permission")

    # 5. Try to create a test event
    print("\n4. Testing Event Creation...")
    try:
        cal_id = os.getenv('GOOGLE_CALENDAR_ID', 'primary')
        start_time = datetime.now() + timedelta(days=1, hours=3)
        end_time = start_time + timedelta(minutes=30)

        event = {
            'summary': 'TEST EVENT - Calendar Integration',
            'description': 'This is a test event created by the calendar debug script',
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
        }

        created = service.events().insert(calendarId=cal_id, body=event).execute()
        print(f"   ✓ Test event created successfully!")
        print(f"   Event ID: {created.get('id')}")
        print(f"   Event Link: {created.get('htmlLink')}")

    except Exception as e:
        print(f"   ❌ Cannot create event: {e}")
        print(f"\n   Error details: {type(e).__name__}")

except Exception as e:
    print(f"   ❌ Failed to initialize: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("DEBUG COMPLETE")
print("=" * 60)
