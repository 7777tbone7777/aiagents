# Google Calendar Integration Setup Guide

This guide explains how to set up and use the Google Calendar integration in `ag.py`.

## Overview

The AI sales agent now automatically detects when a prospect books an appointment during a phone call and creates a Google Calendar event with:
- Automatic calendar event creation
- Natural language time parsing (e.g., "tomorrow at 3pm")
- Calendar invites sent to leads
- Event links included in follow-up emails
- Integration with existing Google Sheets logging

## Prerequisites

1. **Google Service Account** (same as used for Google Sheets)
   - Already configured at: `/Users/anthony/aiagent/keys/sa-sheets.json`

2. **Required Python Dependencies**
   ```bash
   pip install google-api-python-client google-auth google-auth-httplib2
   ```

## Service Account Calendar Access

The service account needs access to the calendar where events will be created:

### Option 1: Use Your Personal Calendar
1. Open Google Calendar (calendar.google.com)
2. Click on Settings (gear icon) → Settings
3. Click on your calendar name under "Settings for my calendars"
4. Scroll to "Share with specific people"
5. Click "Add people"
6. Add the service account email (found in `/Users/anthony/aiagent/keys/sa-sheets.json` under `client_email`)
7. Set permissions to "Make changes to events"
8. Click "Send"

### Option 2: Create a Dedicated Calendar
1. Open Google Calendar
2. Click the "+" next to "Other calendars"
3. Select "Create new calendar"
4. Name it (e.g., "AI Sales Appointments")
5. Click "Create calendar"
6. Share it with the service account email (same steps as Option 1)
7. Get the calendar ID:
   - Settings → Select the new calendar → Scroll to "Integrate calendar"
   - Copy the Calendar ID (looks like: `abc123@group.calendar.google.com`)
8. Set the env var: `GOOGLE_CALENDAR_ID=abc123@group.calendar.google.com`

## Environment Variables

Add to your `.env` file:

```bash
# Optional: specify which calendar to use (defaults to 'primary')
GOOGLE_CALENDAR_ID=primary
# OR use a specific calendar ID:
# GOOGLE_CALENDAR_ID=abc123@group.calendar.google.com
```

The service account credentials are already configured via:
```bash
GOOGLE_SERVICE_ACCOUNT_FILE=/Users/anthony/aiagent/keys/sa-sheets.json
```

## How It Works

### 1. Automatic Detection
During each conversation turn in the `/ai` endpoint, the system:
- Checks the user's speech for appointment time phrases
- Parses natural language times using regex patterns
- Creates a calendar event if an appointment is detected

### 2. Supported Time Formats

The system can parse:
- **Tomorrow**: "tomorrow at 3pm", "tomorrow at 3 p.m.", "tomorrow at 2:30pm"
- **Day of week**: "Friday at 4pm", "Monday at 10:30am"
- **Next week**: "next Tuesday at 2pm", "next Friday at 9am"

Examples from conversation:
- User: "Sure, how about tomorrow at 3pm?"
- User: "I'm free Friday at 2:30 in the afternoon"
- User: "Let's do next Tuesday at 10am"

### 3. Calendar Event Details

Each event includes:
- **Title**: "Follow-up: [Lead Name] - [Company]"
- **Duration**: 30 minutes (default)
- **Description**: Lead details + product pitch + conversation summary
- **Attendees**: Lead's email (if provided)
- **Reminders**:
  - Email reminder 1 day before
  - Popup reminder 30 minutes before
- **Time Zone**: America/Los_Angeles (configurable in code)

### 4. Follow-up Integration

When an appointment is created:
- **SMS**: Updated to include appointment time
- **Email**: Includes appointment confirmation and calendar event link
- **Google Sheets**: Disposition column includes appointment timestamp

## Code Structure

### Key Functions

1. **`parse_appointment_time(text: str) -> dict`**
   - Parses natural language time from conversation
   - Returns: `{'datetime': datetime_obj, 'raw_text': str}` or `None`

2. **`create_calendar_event(lead: dict, appointment_time: datetime, summary: str) -> dict`**
   - Creates the actual calendar event via Google Calendar API
   - Returns: `{'success': bool, 'event_id': str, 'link': str, 'error': str}`

3. **`detect_and_create_appointment(call_sid: str, conversation_text: str) -> dict`**
   - Main function called during conversation
   - Detects appointment, creates event, stores in session
   - Returns: `{'created': bool, 'event_link': str, 'appointment_time': datetime}`

### Integration Points

1. **Session Storage** (line 109-115)
   - Added `"appointment": None` to session structure
   - Stores: `{'time': datetime, 'event_id': str, 'event_link': str}`

2. **AI Endpoint** (line 589-594)
   - Checks each user speech turn for appointments
   - Only creates one appointment per call (checks `if not appointment`)

3. **Follow-up Function** (line 492-544)
   - Customizes SMS/email based on appointment status
   - Includes calendar event link in email

## Testing

### 1. Verify Service Account Access
```python
# Test script
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_service_account_file(
    '/Users/anthony/aiagent/keys/sa-sheets.json',
    scopes=['https://www.googleapis.com/auth/calendar']
)
service = build('calendar', 'v3', credentials=creds)

# List calendars
calendar_list = service.calendarList().list().execute()
for calendar in calendar_list.get('items', []):
    print(f"Calendar: {calendar['summary']} (ID: {calendar['id']})")
```

### 2. Test Time Parsing
```python
from ag import parse_appointment_time

test_phrases = [
    "tomorrow at 3pm",
    "Friday at 2:30 p.m.",
    "next Tuesday at 10am"
]

for phrase in test_phrases:
    result = parse_appointment_time(phrase)
    if result:
        print(f"✓ '{phrase}' → {result['datetime']}")
    else:
        print(f"✗ '{phrase}' → No match")
```

### 3. Make a Test Call
```bash
curl -X POST "http://localhost:5000/outbound?to=+1XXXXXXXXXX&lead_name=TestLead&company=TestCo&email=test@example.com"
```

During the call, say: "Sure, let's meet tomorrow at 3pm"

Check:
- Terminal logs for "Calendar event created"
- Google Calendar for new event
- Follow-up email for calendar link

## Customization

### Change Meeting Duration
Edit line 288 in `ag.py`:
```python
event_end = (appointment_time + timedelta(minutes=60)).isoformat()  # 60-min meeting
```

### Change Time Zone
Edit lines 311 and 315 in `ag.py`:
```python
'timeZone': 'America/New_York',  # Or your preferred timezone
```

### Add More Time Patterns
Add regex patterns to `parse_appointment_time()` function (lines 195-268).

Example for "today at X":
```python
# Add after line 217
today_pattern = r'today\s+at\s+(\d{1,2})(?::(\d{2}))?\s*([ap]\.?\s*m\.?)'
match = re.search(today_pattern, text_lower)
if match:
    # Similar logic to tomorrow_pattern
    ...
```

## Troubleshooting

### Calendar events not created
1. Check service account has calendar access
2. Verify `GOOGLE_SERVICE_ACCOUNT_FILE` path is correct
3. Check terminal logs for "Calendar init skipped" errors
4. Ensure `google-api-python-client` is installed

### Time parsing not working
1. Check terminal logs for "Appointment detected" messages
2. Test `parse_appointment_time()` function directly
3. Verify the user's speech includes supported patterns
4. Check Twilio speech transcription accuracy

### Wrong timezone for events
1. Update timezone in `create_calendar_event()` function
2. Consider using lead's timezone if available

## Security Notes

- Service account credentials have limited calendar access
- Events are only created when appointments are explicitly mentioned
- Calendar invites are only sent if lead email is provided
- All calendar operations are logged for audit trail

## Future Enhancements

Consider adding:
- [ ] Timezone detection based on lead's phone number area code
- [ ] Configurable meeting duration based on conversation context
- [ ] Support for date ranges ("sometime next week")
- [ ] Meeting location/video conference link integration
- [ ] Appointment confirmation/rescheduling via SMS
- [ ] Calendar availability checking before booking
