# Google Calendar Integration - Changes Summary

## Overview
Modified `/Users/anthony/aiagent/ag.py` to automatically detect appointment bookings during phone calls and create Google Calendar events.

## Files Modified

### 1. `/Users/anthony/aiagent/ag.py`

#### Import Changes (Line 59-60)
**Added:**
- `re` module for regex pattern matching
- `timedelta` from datetime for date calculations

```python
import os, io, time, uuid, json, hashlib, smtplib, re
from datetime import datetime, timedelta
```

#### Documentation Updates (Lines 17-26, 34-35)
**Added:**
- Calendar integration section explaining automatic detection
- Environment variable documentation for `GOOGLE_CALENDAR_ID`

#### Session Structure (Line 114)
**Added:**
```python
"appointment": None,  # Will store: {'time': datetime, 'event_id': str, 'event_link': str}
```

#### Google Calendar Integration Section (Lines 157-396)

**Added 3 main sections:**

1. **Calendar Service Initialization (Lines 168-182)**
```python
calendar_service = None
try:
    from googleapiclient.discovery import build
    from google.oauth2.service_account import Credentials as CalendarCredentials

    def _init_calendar():
        # Uses same service account as Google Sheets
        # Supports both GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SERVICE_ACCOUNT_FILE
        ...

    calendar_service = _init_calendar()
except Exception as e:
    log("Calendar init skipped", error=str(e))
```

2. **Natural Language Time Parser (Lines 184-268)**
```python
def parse_appointment_time(text: str) -> dict:
    """
    Parse natural language appointment times from conversation text.

    Supports:
    - "tomorrow at 3pm", "tomorrow at 3 p.m."
    - "tomorrow at 2:30pm"
    - "next Tuesday at 10am"
    - "Friday at 4 p.m."

    Returns: {'datetime': datetime_obj, 'raw_text': str} or None
    """
```

Features:
- Regex patterns for "tomorrow at X" format
- Regex patterns for day-of-week (e.g., "Friday at X")
- Handles "next [day]" format
- Converts 12-hour to 24-hour format
- Calculates correct future date

3. **Calendar Event Creator (Lines 270-351)**
```python
def create_calendar_event(lead: dict, appointment_time: datetime,
                         conversation_summary: str = "") -> dict:
    """
    Create a Google Calendar event for the appointment.

    Returns: {
        'success': bool,
        'event_id': str,
        'link': str,
        'error': str
    }
    """
```

Features:
- Creates 30-minute meetings by default
- Title: "Follow-up: [Lead Name] - [Company]"
- Includes lead details, product pitch, and conversation summary
- Sends calendar invites to lead's email
- Sets reminders (1 day before + 30 min before)
- Configurable timezone (default: America/Los_Angeles)
- Uses env var `GOOGLE_CALENDAR_ID` (default: 'primary')

4. **Detection & Integration Function (Lines 353-396)**
```python
def detect_and_create_appointment(call_sid: str, conversation_text: str) -> dict:
    """
    Detect appointment booking in conversation and create calendar event.

    Returns: {
        'created': bool,
        'event_link': str,
        'appointment_time': datetime
    }
    """
```

#### AI Endpoint Integration (Lines 589-594)
**Added after agent response:**
```python
# Check for appointment booking in user speech
if user_text and not SESSIONS[call_sid].get("appointment"):
    appointment_result = detect_and_create_appointment(call_sid, user_text)
    if appointment_result['created']:
        log("Appointment detected and created", call_sid=call_sid,
            appointment_time=appointment_result['appointment_time'].isoformat())
```

Logic:
- Checks each user speech turn for appointment phrases
- Only creates one appointment per call (`if not appointment`)
- Logs successful creation with timestamp

#### Follow-up Function Enhancement (Lines 492-544)
**Modified `finalize_and_follow_up()` to:**

1. **Check for appointment** (Line 497):
```python
appointment = sess.get("appointment")
```

2. **Customize SMS** (Lines 500-504):
```python
if appointment:
    apt_time = appointment['time'].strftime('%A, %B %d at %I:%M %p')
    sms_message = f"Thanks for your time! Your appointment is scheduled for {apt_time}. Calendar invite sent to your email."
```

3. **Customize Email** (Lines 519-530):
```python
if appointment:
    apt_time = appointment['time'].strftime('%A, %B %d, %Y at %I:%M %p')
    email_body += f"""
APPOINTMENT CONFIRMED
We've scheduled a follow-up meeting for {apt_time}.

Calendar Event: {appointment.get('event_link', 'Check your calendar')}

Looking forward to our conversation!
"""
```

4. **Log Appointment in Disposition** (Lines 540-542):
```python
if appointment:
    disposition_text += f" | Appointment: {appointment['time'].isoformat()}"
```

## Files Created

### 1. `/Users/anthony/aiagent/CALENDAR_SETUP.md`
Comprehensive documentation covering:
- Overview and prerequisites
- Service account calendar access setup
- Environment variables
- How it works (detection, parsing, event creation)
- Supported time formats with examples
- Code structure and integration points
- Testing procedures
- Customization guide
- Troubleshooting
- Future enhancement ideas

### 2. `/Users/anthony/aiagent/INSTALL_CALENDAR.md`
Quick installation guide with:
- Dependency installation commands
- Verification steps
- Service account access granting instructions
- Testing procedures
- Troubleshooting common errors

### 3. `/Users/anthony/aiagent/CALENDAR_CHANGES.md` (this file)
Summary of all changes made to the codebase

## Dependencies Added

Install with:
```bash
pip install google-api-python-client google-auth google-auth-httplib2
```

These packages provide:
- `googleapiclient.discovery` - Google Calendar API client
- `google.oauth2.service_account` - Service account authentication

## Environment Variables

### Required (Already Configured)
- `GOOGLE_SERVICE_ACCOUNT_FILE=/Users/anthony/aiagent/keys/sa-sheets.json`
  - Same service account used for Google Sheets
  - Needs Calendar API scope added

### Optional (New)
- `GOOGLE_CALENDAR_ID=primary` (default)
  - Specify which calendar to create events in
  - Use 'primary' for personal calendar
  - Or use specific calendar ID (e.g., `abc123@group.calendar.google.com`)

## Key Features

### 1. Automatic Detection
- Monitors every conversation turn for appointment phrases
- No manual intervention required
- Works seamlessly with existing call flow

### 2. Natural Language Processing
Supports conversational time formats:
- "tomorrow at 3pm" → Creates event for next day at 3:00 PM
- "Friday at 2:30 p.m." → Creates event for next Friday at 2:30 PM
- "next Tuesday at 10am" → Creates event for Tuesday next week at 10:00 AM

### 3. Comprehensive Event Details
Each calendar event includes:
- Lead's name and company in title
- Lead contact information in description
- Product pitch reminder
- Recent conversation summary
- 30-minute duration
- Automatic reminders (1 day + 30 min before)
- Calendar invite sent to lead's email

### 4. Integrated Follow-ups
- SMS mentions appointment time
- Email includes appointment confirmation
- Calendar event link in email
- Appointment logged to Google Sheets

## Testing Recommendations

1. **Install dependencies:**
   ```bash
   pip install google-api-python-client google-auth google-auth-httplib2
   ```

2. **Grant calendar access to service account:**
   - Get email from `/Users/anthony/aiagent/keys/sa-sheets.json`
   - Share calendar with that email (make changes permission)

3. **Test time parsing:**
   ```python
   from ag import parse_appointment_time
   result = parse_appointment_time("tomorrow at 3pm")
   print(result)  # Should show datetime object
   ```

4. **Make test call:**
   ```bash
   curl -X POST "http://localhost:5000/outbound?to=+1XXXXXXXXXX&lead_name=John&company=TestCo&email=john@test.com"
   ```
   During call, say: "Sure, let's meet tomorrow at 3pm"

5. **Verify:**
   - Check terminal logs for "Calendar event created"
   - Check Google Calendar for new event
   - Check follow-up email for calendar link
   - Check Google Sheets for appointment in disposition column

## Code Quality

- **Error Handling**: All calendar operations wrapped in try/except
- **Graceful Degradation**: System continues working if calendar service unavailable
- **Logging**: All calendar actions logged for debugging
- **Session Isolation**: One appointment per call (prevents duplicates)
- **Reusability**: Functions are modular and well-documented

## Security Considerations

- Service account has limited calendar access only
- Events only created when explicitly mentioned in conversation
- Calendar invites only sent if lead email provided
- All operations logged for audit trail
- Same security model as existing Google Sheets integration

## Future Enhancement Ideas

From `CALENDAR_SETUP.md`:
- Timezone detection based on lead's phone number
- Configurable meeting duration based on context
- Support for date ranges ("sometime next week")
- Video conference link integration
- Appointment confirmation/rescheduling via SMS
- Calendar availability checking before booking
