# Google Calendar Integration - Quick Start

## 1-Minute Setup

### Step 1: Install Dependencies
```bash
cd /Users/anthony/aiagent
source venv/bin/activate
pip install google-api-python-client google-auth google-auth-httplib2
```

### Step 2: Grant Calendar Access

1. Get your service account email:
```bash
cat /Users/anthony/aiagent/keys/sa-sheets.json | grep client_email
```

2. Go to https://calendar.google.com
3. Click ⚙️ Settings → Your calendar name
4. Scroll to "Share with specific people"
5. Add the service account email with "Make changes to events" permission

### Step 3: Test the Setup
```bash
python test_calendar.py
```

If all tests pass, you're ready!

### Step 4: Start the Server
```bash
python ag.py
```

## How to Use

During a phone call, when a lead says any of these:
- "tomorrow at 3pm"
- "Friday at 2:30"
- "next Tuesday at 10am"

The system will:
1. ✅ Automatically detect the appointment time
2. ✅ Create a Google Calendar event
3. ✅ Send calendar invite to lead's email
4. ✅ Include event link in follow-up email
5. ✅ Log appointment to Google Sheets

## Verification

After a test call, check:
- [ ] Terminal shows: `Calendar event created`
- [ ] Google Calendar has the new event
- [ ] Lead receives calendar invite email
- [ ] Follow-up email includes event link
- [ ] Google Sheets shows appointment in disposition

## Supported Time Formats

The system understands:
- ✅ "tomorrow at 3pm"
- ✅ "tomorrow at 3 p.m."
- ✅ "tomorrow at 2:30pm"
- ✅ "Friday at 4pm"
- ✅ "Monday at 9:30 a.m."
- ✅ "next Tuesday at 10am"

## Troubleshooting

**"Calendar init skipped" in logs**
→ Run: `pip install google-api-python-client google-auth`

**"403 Forbidden" when creating events**
→ Grant calendar access to service account (see Step 2)

**Time parsing not working**
→ Check that lead says exact time format (e.g., "3pm" not "three")

## Files Changed

- ✏️ Modified: `/Users/anthony/aiagent/ag.py`
  - Added calendar integration functions
  - Integrated appointment detection into call flow
  - Enhanced follow-up emails with calendar links

## Documentation

- 📖 `CALENDAR_SETUP.md` - Comprehensive setup guide
- 📦 `INSTALL_CALENDAR.md` - Installation instructions
- 📝 `CALENDAR_CHANGES.md` - Detailed change log
- 🧪 `test_calendar.py` - Test script

## Environment Variables

Already configured (from Google Sheets setup):
```bash
GOOGLE_SERVICE_ACCOUNT_FILE=/Users/anthony/aiagent/keys/sa-sheets.json
```

Optional (add to .env if needed):
```bash
GOOGLE_CALENDAR_ID=primary  # or specific calendar ID
```

## What Gets Created

Each calendar event includes:
- **Title**: "Follow-up: [Name] - [Company]"
- **Duration**: 30 minutes
- **Attendees**: Lead's email
- **Reminders**: 1 day before + 30 min before
- **Description**: Lead details + conversation summary
- **Timezone**: America/Los_Angeles (configurable in code)

## Support

If you encounter issues:
1. Run `python test_calendar.py` to diagnose
2. Check logs for error messages
3. See `CALENDAR_SETUP.md` troubleshooting section
4. Verify service account has calendar access

---

**Ready to test?** Make a call and say "tomorrow at 3pm" to see it in action!
