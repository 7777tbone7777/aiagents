# Quick Installation Guide for Calendar Integration

## Install Required Dependencies

The calendar integration requires the Google API client libraries. Install them with:

```bash
# Activate your virtual environment first
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Google Calendar API dependencies
pip install google-api-python-client google-auth google-auth-httplib2 google-auth-oauthlib
```

## Verify Installation

Test that the calendar service can initialize:

```bash
python3 -c "
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import os

# Load credentials
creds = Credentials.from_service_account_file(
    '/Users/anthony/aiagent/keys/sa-sheets.json',
    scopes=['https://www.googleapis.com/auth/calendar']
)

# Build service
service = build('calendar', 'v3', credentials=creds)
print('✓ Calendar service initialized successfully')

# List accessible calendars
calendar_list = service.calendarList().list().execute()
print(f'✓ Found {len(calendar_list.get(\"items\", []))} accessible calendars')
"
```

## Grant Calendar Access to Service Account

1. Get your service account email from the credentials file:
```bash
cat /Users/anthony/aiagent/keys/sa-sheets.json | grep client_email
```

2. Go to Google Calendar (calendar.google.com)

3. Click Settings (gear icon) → Settings

4. Under "Settings for my calendars", click on the calendar you want to use

5. Scroll to "Share with specific people" → Click "Add people"

6. Paste the service account email

7. Set permission to "Make changes to events"

8. Click "Send"

## Test the Integration

Start the server:
```bash
python ag.py
```

Make a test call and during conversation, say one of these phrases:
- "Sure, let's meet tomorrow at 3pm"
- "How about Friday at 2:30?"
- "I'm available next Tuesday at 10am"

Check:
1. Terminal logs should show: `Calendar event created`
2. Google Calendar should have a new event
3. Follow-up email should include calendar event link

## Environment Variables

Optional: Specify which calendar to use (defaults to 'primary'):

```bash
# Add to .env file
GOOGLE_CALENDAR_ID=primary

# Or use a specific calendar ID (get from calendar settings):
# GOOGLE_CALENDAR_ID=abc123@group.calendar.google.com
```

## Complete Dependency List for ag.py

If starting fresh, install all dependencies:

```bash
pip install flask twilio openai requests python-dotenv gspread google-auth sendgrid google-api-python-client google-auth-httplib2
```

## Troubleshooting

**Error: "Module not found: googleapiclient"**
```bash
pip install google-api-python-client
```

**Error: "Calendar init skipped"**
- Check that `GOOGLE_SERVICE_ACCOUNT_FILE` path is correct
- Verify the service account JSON file exists
- Check file permissions: `ls -l /Users/anthony/aiagent/keys/sa-sheets.json`

**Error: "403: Forbidden" when creating events**
- Service account doesn't have calendar access
- Follow the "Grant Calendar Access" steps above

**Events created but in wrong timezone**
- Edit `ag.py` line 311 and 315 to change timezone
- Default is `America/Los_Angeles`

## Next Steps

See `CALENDAR_SETUP.md` for detailed documentation on:
- How the integration works
- Supported time formats
- Customization options
- Security considerations
