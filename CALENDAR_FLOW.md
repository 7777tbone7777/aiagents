# Google Calendar Integration - Call Flow

## Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    INBOUND CALL STARTS                          │
│                    /outbound endpoint                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GREETING DELIVERED                            │
│                    /voice endpoint                               │
│  "Hi John, this is Ava with XR Pay..."                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  CONVERSATION LOOP                               │
│                  /ai endpoint (MODIFIED)                         │
└─────────────────────────────────────────────────────────────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
    ┌───────────────┐              ┌──────────────────┐
    │ User Speech:  │              │  User Speech:    │
    │ "How does it  │              │  "Sure, tomorrow │
    │  work?"       │              │   at 3pm works"  │
    └───────┬───────┘              └────────┬─────────┘
            │                               │
            ▼                               ▼
    ┌──────────────────┐          ┌─────────────────────────┐
    │ Transcribe       │          │ Transcribe              │
    │ Store in history │          │ Store in history        │
    │ Call OpenAI      │          │ Call OpenAI             │
    │ Generate TTS     │          │ Generate TTS            │
    │                  │          │                         │
    │ ❌ No appointment│          │ ✅ APPOINTMENT DETECTED │
    │    detected      │          │                         │
    └──────────────────┘          └────────┬────────────────┘
                                           │
                                           ▼
                              ┌─────────────────────────────┐
                              │ parse_appointment_time()    │
                              │ - Regex match: "tomorrow at"│
                              │ - Extract: 3pm              │
                              │ - Convert to datetime       │
                              │ - Returns: 2025-10-21 15:00│
                              └────────┬────────────────────┘
                                       │
                                       ▼
                              ┌─────────────────────────────┐
                              │ create_calendar_event()     │
                              │ - Build event object        │
                              │ - Title: "Follow-up: John - │
                              │          Acme Corp"         │
                              │ - Duration: 30 min          │
                              │ - Attendees: john@acme.com  │
                              │ - Reminders: 1 day, 30 min  │
                              │ - Call Google Calendar API  │
                              └────────┬────────────────────┘
                                       │
                                       ▼
                              ┌─────────────────────────────┐
                              │ ✅ Event Created            │
                              │ - Event ID: abc123          │
                              │ - Link: calendar.google.com/│
                              │         event?eid=abc123    │
                              │                             │
                              │ Store in session:           │
                              │ session['appointment'] = {  │
                              │   'time': datetime_obj,     │
                              │   'event_id': 'abc123',     │
                              │   'event_link': 'https://...'│
                              │ }                           │
                              └────────┬────────────────────┘
                                       │
                                       ▼
                              ┌─────────────────────────────┐
                              │ Log to console:             │
                              │ "Calendar event created"    │
                              │ call_sid=CAxxxx             │
                              │ event_id=abc123             │
                              │ appointment_time=2025-10-21T│
                              │                  15:00:00   │
                              └─────────────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            │                                                      │
            ▼                                                      ▼
    Continue conversation...                      Continue conversation...

                             │
                             │ (Call ends - silence or opt-out)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CALL COMPLETED                                │
│                    /status endpoint                              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              finalize_and_follow_up() (MODIFIED)                 │
└─────────────────────────────────────────────────────────────────┘
                             │
            ┌────────────────┴────────────────┐
            │                                 │
            ▼                                 ▼
    ┌──────────────────┐          ┌──────────────────────┐
    │ No appointment   │          │ Appointment exists   │
    │                  │          │                      │
    │ SMS:             │          │ SMS:                 │
    │ "Thanks for your │          │ "Your appointment is │
    │  time - XR Pay"  │          │  scheduled for       │
    │                  │          │  Wednesday, Oct 21   │
    │ EMAIL:           │          │  at 03:00 PM"        │
    │ - Recap          │          │                      │
    │ - Product pitch  │          │ EMAIL:               │
    │ - "Would you be  │          │ - Recap              │
    │    open to a     │          │ - Product pitch      │
    │    follow-up?"   │          │ - APPOINTMENT        │
    │                  │          │   CONFIRMED          │
    │ SHEETS LOG:      │          │ - "Wednesday, Oct 21,│
    │ disposition=""   │          │    2025 at 03:00 PM" │
    │                  │          │ - Calendar link      │
    │                  │          │                      │
    │                  │          │ SHEETS LOG:          │
    │                  │          │ disposition=         │
    │                  │          │  "| Appointment:     │
    │                  │          │   2025-10-21T15:00"  │
    └──────────────────┘          └──────────────────────┘
```

## Code Execution Path

### 1. During Conversation (/ai endpoint)
```python
# Lines 589-594 in ag.py

@APP.post("/ai")
def ai():
    # ... existing code to process speech ...

    # ✨ NEW: Check for appointment booking
    if user_text and not SESSIONS[call_sid].get("appointment"):
        appointment_result = detect_and_create_appointment(call_sid, user_text)
        if appointment_result['created']:
            log("Appointment detected and created", ...)
```

### 2. Appointment Detection Function
```python
# Lines 353-396 in ag.py

def detect_and_create_appointment(call_sid, conversation_text):
    # Step 1: Parse natural language time
    appointment_info = parse_appointment_time(conversation_text)
    #   Input: "tomorrow at 3pm"
    #   Output: {'datetime': 2025-10-21 15:00:00, 'raw_text': 'tomorrow at 3pm'}

    if not appointment_info:
        return {'created': False, ...}

    # Step 2: Get lead info and conversation summary
    lead = SESSIONS[call_sid]['lead']
    summary = "\n".join([f"{r}: {t}" for r, t in history][-10:])

    # Step 3: Create calendar event
    result = create_calendar_event(lead, appointment_info['datetime'], summary)
    #   Calls Google Calendar API
    #   Creates 30-min event with reminders
    #   Sends invite to lead

    # Step 4: Store in session
    if result['success']:
        SESSIONS[call_sid]['appointment'] = {
            'time': appointment_info['datetime'],
            'event_id': result['event_id'],
            'event_link': result['link']
        }
        return {'created': True, 'event_link': result['link'], ...}
```

### 3. Time Parsing Logic
```python
# Lines 184-268 in ag.py

def parse_appointment_time(text):
    text_lower = text.lower()

    # Pattern 1: "tomorrow at 3pm"
    match = re.search(r'tomorrow\s+at\s+(\d{1,2})(?::(\d{2}))?\s*([ap]\.?\s*m\.?)',
                     text_lower)
    if match:
        hour = int(match.group(1))      # 3
        am_pm = match.group(3)          # "pm"

        # Convert to 24-hour
        if 'p' in am_pm and hour != 12:
            hour += 12                   # 3 + 12 = 15 (3pm)

        # Calculate tomorrow's date
        appointment_dt = datetime.now() + timedelta(days=1)
        appointment_dt = appointment_dt.replace(hour=15, minute=0, ...)

        return {'datetime': appointment_dt, 'raw_text': 'tomorrow at 3pm'}

    # Pattern 2: "Friday at 4pm"
    # ... similar logic for day-of-week ...

    return None  # No match found
```

### 4. Calendar Event Creation
```python
# Lines 270-351 in ag.py

def create_calendar_event(lead, appointment_time, conversation_summary):
    # Build event object
    event = {
        'summary': f"Follow-up: {lead['name']} - {lead['company']}",
        'description': f"""Lead: {lead['name']}
                          Company: {lead['company']}
                          Email: {lead['email']}
                          Phone: {lead['phone']}

                          Conversation:
                          {conversation_summary}""",
        'start': {
            'dateTime': '2025-10-21T15:00:00',
            'timeZone': 'America/Los_Angeles',
        },
        'end': {
            'dateTime': '2025-10-21T15:30:00',  # +30 minutes
            'timeZone': 'America/Los_Angeles',
        },
        'attendees': [
            {'email': lead['email']}
        ],
        'reminders': {
            'overrides': [
                {'method': 'email', 'minutes': 1440},  # 1 day
                {'method': 'popup', 'minutes': 30},    # 30 min
            ],
        },
    }

    # Call Google Calendar API
    created_event = calendar_service.events().insert(
        calendarId='primary',
        body=event,
        sendUpdates='all'  # Send invite to attendees
    ).execute()

    return {
        'success': True,
        'event_id': created_event['id'],
        'link': created_event['htmlLink']
    }
```

### 5. Follow-up Enhancement
```python
# Lines 492-544 in ag.py

def finalize_and_follow_up(call_sid):
    appointment = SESSIONS[call_sid].get('appointment')

    if appointment:
        # Customize SMS
        apt_time = appointment['time'].strftime('%A, %B %d at %I:%M %p')
        sms = f"Your appointment is scheduled for {apt_time}. Calendar invite sent."

        # Customize Email
        email_body = f"""
        APPOINTMENT CONFIRMED
        We've scheduled a follow-up meeting for {apt_time}.

        Calendar Event: {appointment['event_link']}

        Looking forward to our conversation!
        """

        # Log to Sheets with appointment info
        disposition = f"| Appointment: {appointment['time'].isoformat()}"
```

## Key Features

### 🎯 Automatic Detection
- Monitors every user speech turn
- No manual triggering required
- Works seamlessly in conversation flow

### 🧠 Natural Language Processing
- Regex-based pattern matching
- Supports multiple time formats
- Converts to proper datetime objects

### 📅 Calendar Integration
- Uses Google Calendar API v3
- Same service account as Sheets
- Automatic invite sending
- Customizable reminders

### 📧 Enhanced Follow-ups
- SMS includes appointment time
- Email has calendar event link
- Google Sheets logs appointment

### 🛡️ Safety Features
- Only one appointment per call
- Graceful error handling
- Falls back if calendar unavailable
- All operations logged

## Example Conversation

```
Agent: "Hi John, this is Ava with XR Pay. We provide film & TV payroll
        with modern tooling. Do you have a quick minute?"

User:  "Sure, what can you tell me?"

Agent: "We cut invoice time in half for production teams. Would you be
        open to a 15-minute walkthrough?"

User:  "Yeah, how about tomorrow at 3pm?"
       ⬆️ APPOINTMENT DETECTED

[System automatically:]
✅ Parses "tomorrow at 3pm" → 2025-10-21 15:00:00
✅ Creates calendar event
✅ Sends invite to john@acme.com
✅ Stores in session
✅ Logs: "Calendar event created call_sid=CAxxxx event_id=abc123"

Agent: "Perfect, I'll send you a calendar invite. Looking forward to it!"

[Call ends - system automatically:]
📱 SMS: "Your appointment is scheduled for Wednesday, October 21 at 03:00 PM"
📧 Email: Includes calendar link and appointment confirmation
📊 Sheets: Logs disposition with appointment timestamp
```

## Data Flow

```
User Speech
    ↓
Twilio Transcription
    ↓
/ai endpoint receives text
    ↓
detect_and_create_appointment(call_sid, text)
    ↓
parse_appointment_time(text) → datetime object
    ↓
create_calendar_event(lead, datetime, summary)
    ↓
Google Calendar API → Creates event
    ↓
Store in session['appointment']
    ↓
[Call continues normally...]
    ↓
Call ends → /status callback
    ↓
finalize_and_follow_up(call_sid)
    ↓
Check if appointment exists
    ↓
Customize SMS/Email with appointment details
    ↓
Send follow-ups with calendar link
    ↓
Log to Google Sheets with appointment timestamp
```
