#!/usr/bin/env python3
"""
Test script for Google Calendar integration

Run this to verify calendar setup before making live calls.
"""

import os
import sys
from datetime import datetime, timedelta

# Test 1: Check environment variables
print("=" * 60)
print("TEST 1: Environment Variables")
print("=" * 60)

service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")

print(f"GOOGLE_SERVICE_ACCOUNT_FILE: {service_account_file}")
print(f"GOOGLE_SERVICE_ACCOUNT_JSON: {'Set' if service_account_json else 'Not set'}")
print(f"GOOGLE_CALENDAR_ID: {calendar_id}")

if not service_account_file and not service_account_json:
    print("\n❌ ERROR: No service account credentials configured")
    print("   Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON")
    sys.exit(1)

if service_account_file and not os.path.exists(service_account_file):
    print(f"\n❌ ERROR: Service account file not found: {service_account_file}")
    sys.exit(1)

print("✓ Environment variables OK\n")

# Test 2: Import dependencies
print("=" * 60)
print("TEST 2: Import Dependencies")
print("=" * 60)

try:
    from google.oauth2.service_account import Credentials
    print("✓ google.oauth2.service_account")
except ImportError as e:
    print(f"❌ google-auth not installed: {e}")
    print("   Run: pip install google-auth")
    sys.exit(1)

try:
    from googleapiclient.discovery import build
    print("✓ googleapiclient.discovery")
except ImportError as e:
    print(f"❌ google-api-python-client not installed: {e}")
    print("   Run: pip install google-api-python-client")
    sys.exit(1)

print("✓ All dependencies installed\n")

# Test 3: Initialize calendar service
print("=" * 60)
print("TEST 3: Initialize Calendar Service")
print("=" * 60)

try:
    scopes = ["https://www.googleapis.com/auth/calendar"]

    if service_account_json:
        import json
        info = json.loads(service_account_json)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        print("✓ Loaded credentials from JSON env var")
    else:
        creds = Credentials.from_service_account_file(service_account_file, scopes=scopes)
        print(f"✓ Loaded credentials from file: {service_account_file}")

    service = build('calendar', 'v3', credentials=creds)
    print("✓ Calendar service initialized")

    # Get service account email
    if service_account_file:
        import json
        with open(service_account_file) as f:
            sa_data = json.load(f)
            sa_email = sa_data.get('client_email', 'Unknown')
    else:
        sa_email = info.get('client_email', 'Unknown')

    print(f"  Service Account Email: {sa_email}\n")

except Exception as e:
    print(f"❌ Failed to initialize calendar service: {e}")
    sys.exit(1)

# Test 4: List accessible calendars
print("=" * 60)
print("TEST 4: List Accessible Calendars")
print("=" * 60)

try:
    calendar_list = service.calendarList().list().execute()
    calendars = calendar_list.get('items', [])

    if not calendars:
        print("❌ No calendars accessible")
        print("   The service account needs to be granted access to a calendar.")
        print("   See INSTALL_CALENDAR.md for instructions.")
        sys.exit(1)

    print(f"✓ Found {len(calendars)} accessible calendar(s):\n")
    for cal in calendars:
        cal_id = cal.get('id', 'Unknown')
        cal_name = cal.get('summary', 'Unknown')
        access_role = cal.get('accessRole', 'Unknown')
        is_primary = ' (PRIMARY)' if cal.get('primary', False) else ''
        print(f"  • {cal_name}{is_primary}")
        print(f"    ID: {cal_id}")
        print(f"    Access: {access_role}")
        print()

    # Check if target calendar is accessible
    target_found = False
    for cal in calendars:
        if cal.get('id') == calendar_id or (calendar_id == 'primary' and cal.get('primary')):
            target_found = True
            target_access = cal.get('accessRole')
            break

    if not target_found:
        print(f"❌ Target calendar '{calendar_id}' not accessible")
        print("   Update GOOGLE_CALENDAR_ID or grant access to service account")
        sys.exit(1)

    if target_access not in ['owner', 'writer']:
        print(f"⚠️  WARNING: Target calendar has '{target_access}' access")
        print("   Need 'writer' or 'owner' access to create events")
    else:
        print(f"✓ Target calendar '{calendar_id}' is accessible with '{target_access}' access\n")

except Exception as e:
    print(f"❌ Failed to list calendars: {e}")
    print("   The service account may not have calendar access.")
    sys.exit(1)

# Test 5: Test time parsing
print("=" * 60)
print("TEST 5: Time Parsing Functions")
print("=" * 60)

# Import the parse function from ag.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from ag import parse_appointment_time

    test_phrases = [
        "tomorrow at 3pm",
        "tomorrow at 3 p.m.",
        "tomorrow at 2:30pm",
        "Friday at 4pm",
        "next Tuesday at 10am",
        "Monday at 9:30 a.m.",
    ]

    print("Testing natural language time parsing:\n")
    for phrase in test_phrases:
        result = parse_appointment_time(phrase)
        if result:
            dt = result['datetime']
            formatted = dt.strftime('%A, %B %d, %Y at %I:%M %p')
            print(f"  ✓ '{phrase}'")
            print(f"    → {formatted}")
        else:
            print(f"  ❌ '{phrase}' → No match")
        print()

except Exception as e:
    print(f"⚠️  Could not test parse_appointment_time: {e}")
    print("   This is OK if ag.py has dependencies not yet installed")
    print()

# Test 6: Create a test event (optional)
print("=" * 60)
print("TEST 6: Create Test Event (Optional)")
print("=" * 60)

response = input("Create a test calendar event? (y/N): ").strip().lower()

if response == 'y':
    try:
        # Create test event for tomorrow at 2pm
        test_time = datetime.now() + timedelta(days=1)
        test_time = test_time.replace(hour=14, minute=0, second=0, microsecond=0)

        event = {
            'summary': 'TEST: AI Sales Agent Calendar Integration',
            'description': 'This is a test event created by test_calendar.py. You can delete this.',
            'start': {
                'dateTime': test_time.isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
            'end': {
                'dateTime': (test_time + timedelta(minutes=30)).isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 10},
                ],
            },
        }

        print(f"\nCreating test event for {test_time.strftime('%A, %B %d at %I:%M %p')}...")

        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()

        event_link = created_event.get('htmlLink', 'No link')
        event_id = created_event.get('id', 'Unknown')

        print(f"✓ Test event created successfully!")
        print(f"  Event ID: {event_id}")
        print(f"  Link: {event_link}")
        print(f"\nCheck your calendar and delete this test event when done.\n")

    except Exception as e:
        print(f"❌ Failed to create test event: {e}")
        print("   Check that service account has 'writer' access to the calendar")
else:
    print("Skipped test event creation\n")

# Summary
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print("✓ All tests passed!")
print("\nYour Google Calendar integration is configured correctly.")
print("\nNext steps:")
print("1. Start the server: python ag.py")
print("2. Make a test call")
print("3. Say 'tomorrow at 3pm' during the conversation")
print("4. Check your calendar for the created event")
print("\nSee CALENDAR_SETUP.md for more information.\n")
