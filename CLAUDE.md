# CLAUDE.md

This file provides comprehensive guidance to Claude Code when working with the AI Agents platform.

## Project Overview

**Bolt AI Platform** - A multi-tenant AI voice agent system that enables businesses to have AI-powered phone assistants handle customer calls 24/7. The platform conducts real-time voice conversations, books appointments, answers questions, and provides detailed analytics.

### Three Versions (Evolution)

1. **`app.py`** (11KB) - Prototype
   - Basic Flask app with Twilio voice webhooks
   - OpenAI chat completions API
   - ElevenLabs TTS (with Twilio Polly fallback)
   - In-memory sessions only
   - Best for: Simple demos and testing

2. **`ag.py`** (27KB) - Extended
   - Adds Google Sheets logging
   - SMS/email follow-ups (Twilio + SendGrid)
   - Basic calendar appointment parsing
   - Disposition tracking
   - Best for: Small-scale production with manual tracking

3. **`bolt_realtime.py`** (109KB) - Production Platform ⭐ **CURRENT**
   - FastAPI + WebSocket architecture
   - **OpenAI Realtime API** (sub-second voice responses!)
   - Supabase multi-tenant database
   - Business account system with custom configurations
   - Google Calendar integration with natural language parsing
   - Automated email workflows (instant alerts + daily digests)
   - Railway deployment ready
   - Best for: **Production use with multiple businesses**

---

## Production Platform Architecture (`bolt_realtime.py`)

### Technology Stack

- **Web Framework**: FastAPI (async)
- **Real-time**: WebSocket (Twilio Media Streams ↔ OpenAI Realtime API)
- **Database**: Supabase (PostgreSQL)
- **Voice**: Twilio Programmable Voice
- **AI**: OpenAI Realtime API (`gpt-4o-realtime-preview-2024-10-01`)
- **Calendar**: Google Calendar API
- **Email**: Resend (primary) or SMTP (fallback)
- **Scheduler**: APScheduler (daily digests)
- **Deployment**: Railway

### Database Schema

#### `businesses` Table
Multi-tenant business accounts with custom configurations.

```sql
id                  UUID PRIMARY KEY
business_name       TEXT              -- e.g., "Bolt AI Group"
owner_name          TEXT              -- Business owner's name
owner_email         TEXT              -- For receiving alerts/digests
industry            TEXT              -- barber, restaurant, gym, doctor, etc.
agent_name          TEXT              -- AI agent's name (e.g., "Ava")
capabilities        JSONB             -- ["appointments", "orders", "support"]
google_calendar_id  TEXT              -- Google Calendar email for booking
plan                TEXT              -- pricing tier
status              TEXT              -- active, suspended, cancelled
created_at          TIMESTAMP
updated_at          TIMESTAMP
```

#### `phone_numbers` Table
Maps Twilio phone numbers to businesses.

```sql
id              UUID PRIMARY KEY
business_id     UUID REFERENCES businesses(id)
phone_number    TEXT UNIQUE       -- E.164 format: +1XXXXXXXXXX
status          TEXT              -- active, inactive
created_at      TIMESTAMP
```

#### `calls` Table
Call records with status and duration.

```sql
id              UUID PRIMARY KEY
business_id     UUID REFERENCES businesses(id)
call_sid        TEXT UNIQUE       -- Twilio CallSid
from_number     TEXT              -- Caller's phone
to_number       TEXT              -- Business phone number
direction       TEXT              -- inbound, outbound
status          TEXT              -- in-progress, completed, failed, busy, no-answer
duration        INTEGER           -- Call duration in seconds
created_at      TIMESTAMP
updated_at      TIMESTAMP
```

#### `call_transcripts` Table
Turn-by-turn conversation logs.

```sql
id              UUID PRIMARY KEY
call_id         UUID REFERENCES calls(id)
role            TEXT              -- user, assistant, system
content         TEXT              -- Spoken/generated text
created_at      TIMESTAMP
```

#### `leads` Table
Customer information captured during calls.

```sql
id              UUID PRIMARY KEY
business_id     UUID REFERENCES businesses(id)
phone_number    TEXT
name            TEXT
email           TEXT
company         TEXT
industry        TEXT
notes           TEXT
status          TEXT              -- qualified, not-interested, dnc, callback
created_at      TIMESTAMP
updated_at      TIMESTAMP
```

---

## Call Flow Architecture

### Inbound Call Flow (bolt_realtime.py)

```
1. Customer dials business phone number
   ↓
2. Twilio receives call → webhook POST /inbound
   ↓
3. Server queries database:
   - Lookup business by to_number (phone_numbers table)
   - Load business configuration
   - Create call record in database
   ↓
4. Server returns TwiML with <Connect><Stream>
   - Opens WebSocket connection to /media-stream
   ↓
5. Bi-directional WebSocket established:
   [Twilio Media Stream] ←→ [Server] ←→ [OpenAI Realtime API]
   - Twilio sends audio chunks (mulaw, base64)
   - Server forwards to OpenAI as PCM16
   - OpenAI responds with PCM16 audio + transcripts
   - Server forwards audio back to Twilio
   ↓
6. Real-time conversation happens:
   - Sub-second latency responses
   - Conversation tracked in session
   - Transcripts saved to database
   ↓
7. During conversation:
   - Parse for appointment times ("tomorrow at 3pm")
   - Create Google Calendar event if booking detected
   - Capture lead information (name, email, company)
   ↓
8. Call ends:
   - Update call record (status: completed, duration)
   - Save final transcript
   - Send follow-up email with appointment details
   ↓
9. Post-call automation:
   - Instant email alert to business owner
   - Daily digest scheduled for 9 AM (APScheduler)
```

### Outbound Call Flow (ag.py / app.py)

```
1. HTTP POST /outbound?to=+1XXX&lead_name=John&company=Acme
   ↓
2. Server initiates Twilio call
   ↓
3. Twilio calls customer → webhook POST /voice
   ↓
4. Server returns TwiML with greeting + <Gather input="speech">
   ↓
5. Conversation loop:
   a. Customer speaks → Twilio transcribes
   b. POST /ai with SpeechResult
   c. Server calls OpenAI chat completion
   d. Generate TTS audio (ElevenLabs or Polly)
   e. Return TwiML with audio + <Gather>
   f. Repeat until opt-out or silence
   ↓
6. Call completes → POST /status callback
   ↓
7. Send SMS + email follow-up
```

---

## API Endpoints Reference

### bolt_realtime.py (FastAPI)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/inbound` | Twilio webhook for incoming calls (returns TwiML) |
| POST | `/outbound` | Initiate outbound call (requires business_id, to_number) |
| WS | `/media-stream` | WebSocket for Twilio Media Streams ↔ OpenAI Realtime |
| GET | `/health` | Health check endpoint |
| POST | `/setup-database` | Initialize Supabase tables (dev only) |
| GET | `/` | Dashboard HTML (shows config status) |

### ag.py / app.py (Flask)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/outbound` | Initiate outbound call |
| POST | `/voice` | Twilio webhook for call start (greeting) |
| POST | `/ai` | Conversation loop handler |
| GET | `/audio/<token>.mp3` | Serve cached ElevenLabs audio |
| POST | `/status` | Call completion callback (ag.py only) |
| GET | `/health` | Health check |

---

## Configuration Guide

### Environment Variables

#### Required (All Versions)

```bash
OPENAI_API_KEY=sk-proj-xxx              # OpenAI API key
TWILIO_ACCOUNT_SID=ACxxx                # Twilio account SID
TWILIO_AUTH_TOKEN=xxx                   # Twilio auth token
TWILIO_NUMBER=+1XXXXXXXXXX              # Your Twilio phone number
```

#### Required (bolt_realtime.py only)

```bash
SUPABASE_URL=https://xxx.supabase.co    # Supabase project URL
SUPABASE_SERVICE_ROLE_KEY=xxx           # Supabase service role key (not anon key!)
```

#### Email Configuration (bolt_realtime.py, ag.py)

**Option A: Resend (Recommended)**
```bash
RESEND_API_KEY=re_xxx
FROM_EMAIL=noreply@yourdomain.com
```

**Option B: SMTP Fallback**
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
FROM_EMAIL=your-email@gmail.com
```

#### Google Calendar (bolt_realtime.py, ag.py)

```bash
GOOGLE_CALENDAR_EMAIL=yourbusiness@gmail.com
GOOGLE_CALENDAR_SERVICE_ACCOUNT=/path/to/service-account.json

# OR inline JSON:
GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
```

**Setup Instructions:**
1. Create Google Cloud service account
2. Enable Google Calendar API
3. Share target calendar with service account email
4. Download JSON key file

#### Optional Configuration

```bash
# AI Voice & Behavior
VOICE=echo                              # alloy, echo, fable, onyx, nova, shimmer
TEMPERATURE=0.8                         # 0.0-1.0 (higher = more creative)
OPENAI_MODEL=gpt-4o-mini               # For app.py/ag.py only

# Business Branding
AGENT_NAME=Ava
COMPANY_NAME=Bolt AI Group
PRODUCT_PITCH="Your AI receptionist that never misses a call"
MONTHLY_PRICE=$199

# Call Settings
MAX_CALL_DURATION=3600                  # Max call length in seconds (1 hour)
WEBSOCKET_PING_INTERVAL=20              # WebSocket keepalive (seconds)
WEBSOCKET_PING_TIMEOUT=10

# Deployment
PORT=5000                               # Server port (Railway sets automatically)
PUBLIC_BASE_URL=https://xxx.ngrok.app   # Override auto-detection
RAILWAY_PUBLIC_DOMAIN=xxx.railway.app   # Set by Railway automatically
```

#### ElevenLabs TTS (app.py, ag.py - optional)

```bash
ELEVENLABS_API_KEY=eleven_xxx
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # Rachel voice
```
*Note: bolt_realtime.py uses OpenAI Realtime API's built-in TTS, so ElevenLabs not needed.*

---

## Development Setup

### Prerequisites

```bash
python3 --version   # 3.9+
```

### Installation

```bash
# Clone and navigate to project
cd ~/github-repos/aiagents

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies (production platform)
pip install -r requirements.txt

# OR install manually:
pip install fastapi uvicorn websockets twilio openai supabase resend \
    google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client \
    apscheduler python-dotenv certifi
```

### Local Development

```bash
# 1. Copy environment variables
cp .env.example .env
# Edit .env with your API keys

# 2. Start ngrok (required for Twilio webhooks)
ngrok http 5000
# Copy the https://xxx.ngrok.app URL

# 3. Run the platform
python bolt_realtime.py
# Server starts on http://0.0.0.0:5000

# 4. Configure Twilio webhook
# Go to Twilio Console → Phone Numbers → Your Number
# Set "A CALL COMES IN" webhook to: https://xxx.ngrok.app/inbound
```

### Testing

```bash
# Health check
curl http://localhost:5000/health

# Setup database (first time only)
curl -X POST http://localhost:5000/setup-database

# Place test call (requires business_id from database)
curl -X POST "http://localhost:5000/outbound" \
  -H "Content-Type: application/json" \
  -d '{
    "business_id": "xxx-uuid-xxx",
    "to_number": "+1XXXXXXXXXX",
    "lead_name": "John Doe",
    "lead_company": "Acme Corp"
  }'
```

---

## Deployment (Railway)

### Railway Setup

1. **Create new Railway project**
   ```bash
   railway login
   railway init
   ```

2. **Add Supabase database**
   - Go to Railway dashboard → Add → Supabase
   - Copy connection details

3. **Configure environment variables**
   - Add all required env vars from Configuration Guide above
   - Railway automatically sets: `PORT`, `RAILWAY_PUBLIC_DOMAIN`

4. **Deploy**
   ```bash
   railway up
   ```

5. **Configure Twilio webhook**
   - Get Railway URL: `https://xxx.railway.app`
   - Twilio Console → Phone Numbers → Your Number
   - Set "A CALL COMES IN": `https://xxx.railway.app/inbound`

### Railway Configuration Files

**`Procfile`**
```
web: python bolt_realtime.py
```

**`railway.toml`**
```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "python bolt_realtime.py"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

---

## Business Logic Deep Dive

### System Prompt (bolt_realtime.py:409-430)

The AI agent's behavior is controlled by a dynamic system prompt that adapts based on the business's industry:

```python
# Industry-specific pitches
if industry == "barber" or industry == "salon":
    "Our AI books haircut appointments 24/7, sends reminders..."
elif industry == "restaurant":
    "Our AI takes reservations and takeout orders any time..."
elif industry == "gym":
    "Our AI books class reservations, answers membership questions..."
elif industry == "doctor" or industry == "dental":
    "Our AI schedules patient appointments, handles rescheduling..."
```

**Conversation Steps:**
1. Ask what type of business they have
2. Explain relevant benefits for their industry
3. Ask if they'd like to schedule a demo
4. Capture name and email if interested

### Appointment Parsing (ag.py:195-279)

Natural language time detection using regex patterns:

```python
# Supported patterns:
"tomorrow at 3pm"           → datetime: tomorrow 3:00 PM
"tomorrow at 2:30pm"        → datetime: tomorrow 2:30 PM
"next Tuesday at 10am"      → datetime: next Tuesday 10:00 AM
"Friday at 4 p.m."          → datetime: this Friday 4:00 PM
```

When detected:
1. Parse time string → datetime object
2. Create Google Calendar event (30-min default duration)
3. Store event ID and link in session
4. Include in follow-up email

### Email Workflows (bolt_realtime.py)

**Instant Call Alert** (sent when call starts):
```
Subject: 🔔 Incoming Call Alert - +1XXXXXXXXXX
Content: Caller phone, call time, call SID
Purpose: Real-time notification for business owner
```

**Follow-up Email** (sent after call completes):
```
Subject: Thanks for your time - [Company Name]
Content:
  - Conversation summary
  - Appointment details (if booked) with calendar link
  - Product pitch recap
  - Next steps
```

**Daily Digest** (sent at 9 AM via APScheduler):
```
Subject: 📊 Daily Call Report - [Date] (X calls)
Content:
  - Total calls, completed, failed, in-progress
  - Average call duration
  - Table of recent calls with status
  - Analytics summary
```

### Session Management

**In-Memory Sessions (all versions):**
```python
SESSIONS = {
    "CA1234...": {                    # Twilio CallSid
        "history": deque(maxlen=40),  # Conversation turns
        "lead": {
            "name": "John Doe",
            "company": "Acme",
            "email": "john@acme.com",
            "phone": "+1XXXXXXXXXX"
        },
        "business_id": "uuid-xxx",
        "call_id": "uuid-xxx",
        "appointment": {              # If booked
            "time": datetime,
            "event_id": "google-cal-id",
            "event_link": "https://..."
        },
        "disposition": "qualified"
    }
}
```

**Database Persistence (bolt_realtime.py only):**
- Call records saved to `calls` table
- Transcripts saved to `call_transcripts` table
- Lead info saved to `leads` table
- Sessions cleared from memory after call ends

---

## Key Files Reference

### Main Application Files

- **`bolt_realtime.py`** (109KB) - Production FastAPI platform
  - Lines 29-114: Configuration and globals
  - Lines 151-191: Database query functions
  - Lines 233-302: Email sending logic
  - Lines 409-430: System prompt (industry-specific)
  - Lines 570-750: WebSocket handler for OpenAI Realtime API
  - Lines 800-900: Twilio webhook handlers

- **`ag.py`** (27KB) - Extended Flask version with Sheets logging
  - Lines 131-157: Google Sheets initialization
  - Lines 169-193: Google Calendar initialization
  - Lines 195-279: Appointment time parsing
  - Lines 281-361: Calendar event creation
  - Lines 409-448: AI reply logic with system prompt
  - Lines 515-567: Follow-up email/SMS logic

- **`app.py`** (11KB) - Basic Flask prototype
  - Lines 102-119: System prompt
  - Lines 122-150: AI reply function
  - Lines 154-183: ElevenLabs TTS
  - Lines 210-227: Outbound call initiation
  - Lines 230-274: Voice webhook (greeting)
  - Lines 277-319: AI conversation loop

### Supporting Files

- **`setup_database.py`** - Initialize Supabase schema (run once)
- **`add_demo_business.py`** - Create test business account
- **`bolt_watchdog.py`** - Health monitoring and auto-restart
- **`ngrok_watchdog.py`** - Auto-manage ngrok tunnel for local dev
- **`test_calendar.py`** - Test Google Calendar integration
- **`requirements.txt`** - Python dependencies

### Documentation Files

- **`CLAUDE.md`** - This file (comprehensive guide)
- **`RAILWAY_DEPLOYMENT.md`** - Railway deployment guide
- **`CALENDAR_SETUP.md`** - Google Calendar integration setup
- **`SCALING_GUIDE.md`** - Scaling considerations for production

---

## Troubleshooting

### Common Issues

#### 1. "No module named 'supabase'" (bolt_realtime.py)
```bash
pip install supabase
```

#### 2. Twilio webhook returns 404
- Check PUBLIC_BASE_URL is correct HTTPS URL
- Verify ngrok tunnel is active: `curl http://localhost:4040/api/tunnels`
- Check Twilio webhook URL matches exactly: `https://xxx.ngrok.app/inbound`

#### 3. Supabase connection fails
- Verify `SUPABASE_SERVICE_ROLE_KEY` (not anon key!)
- Check Supabase dashboard → Settings → API
- Ensure tables exist: run `setup_database.py`

#### 4. Google Calendar booking fails
- Service account email must be invited to target calendar
- Check `GOOGLE_CALENDAR_EMAIL` matches shared calendar
- Verify service account JSON is valid

#### 5. Email not sending
- Check Resend API key is valid
- Verify FROM_EMAIL domain is verified in Resend
- Check SMTP credentials if using SMTP fallback
- Review server logs for specific error

#### 6. OpenAI Realtime API connection fails
- Verify `OPENAI_API_KEY` has Realtime API access (requires waitlist approval)
- Check WebSocket connection in logs
- Ensure Twilio Media Streams is enabled on phone number

#### 7. "Railway deployment succeeds but app crashes"
- Check Railway logs: `railway logs`
- Verify all env vars are set in Railway dashboard
- Ensure PORT is not hardcoded (Railway sets dynamically)

### Debug Logging

Enable verbose logging:
```python
# Add to top of file for debugging
import logging
logging.basicConfig(level=logging.DEBUG)
```

View logs:
```bash
# Local development
python bolt_realtime.py  # stdout

# Railway
railway logs --service web
railway logs --tail 100
```

---

## Performance & Scaling

### Current Capacity
- **Concurrent calls**: ~10-20 per instance (WebSocket connections)
- **Database**: Supabase free tier = 500MB, upgrade as needed
- **Email**: Resend free tier = 3,000/month

### Scaling Recommendations

1. **Horizontal scaling** (Railway auto-scaling):
   - Enable Railway autoscaling in dashboard
   - Each instance handles 10-20 calls
   - Load balancer distributes connections

2. **Database optimization**:
   - Add indexes on frequently queried columns
   - Archive old call transcripts monthly
   - Use Supabase connection pooling

3. **Session management**:
   - Move SESSIONS dict to Redis for shared state
   - Enables load balancing across multiple instances

4. **Email rate limiting**:
   - Upgrade Resend plan if >3k emails/month
   - Implement email queue with Celery for high volume

---

## Security Best Practices

1. **API Keys**: Never commit to git, use environment variables
2. **Supabase**: Use service role key (not anon key) server-side only
3. **Twilio**: Validate webhook signatures (not implemented yet)
4. **Google Calendar**: Service account JSON should be in secure storage
5. **Database**: Use RLS policies in Supabase for multi-tenant isolation

---

## Code Modification Guide

### Change Agent Personality
Edit system prompt in `bolt_realtime.py:409-430` or `ag.py:409-430`

### Add New Business Capability
1. Update `businesses.capabilities` JSONB field
2. Modify system prompt to reference new capability
3. Add handling logic in conversation flow

### Customize Email Templates
- Instant alert: `bolt_realtime.py:304-337`
- Follow-up email: `bolt_realtime.py` (search for "send_email" calls)
- Daily digest: `bolt_realtime.py:339-450`

### Add New API Endpoint
```python
@app.post("/your-endpoint")
async def your_endpoint(request: Request):
    # Your logic here
    return JSONResponse({"status": "success"})
```

### Modify Call Flow
- Inbound greeting: `bolt_realtime.py` `/inbound` endpoint
- Conversation logic: WebSocket handler in `/media-stream`
- Post-call actions: Call completion handler

---

## Version History & Upgrade Path

### Migration from app.py → ag.py
- Add Google Sheets environment variables
- Add SendGrid/SMTP configuration
- Update outbound call to include email parameter
- No code changes needed

### Migration from ag.py → bolt_realtime.py
1. Set up Supabase database
2. Run `setup_database.py`
3. Create business account with `add_demo_business.py`
4. Update environment variables (remove Google Sheets, add Supabase)
5. Change Twilio webhooks from `/voice` to `/inbound`
6. Deploy to Railway

**Breaking Changes:**
- Session storage moved from memory to database
- API endpoints changed (Flask → FastAPI)
- Outbound call requires business_id instead of lead params
- TTS changed from ElevenLabs to OpenAI Realtime (faster!)

---

## Additional Resources

- [OpenAI Realtime API Docs](https://platform.openai.com/docs/guides/realtime)
- [Twilio Media Streams Guide](https://www.twilio.com/docs/voice/media-streams)
- [Supabase Python Client](https://supabase.com/docs/reference/python/introduction)
- [Railway Deployment Docs](https://docs.railway.app/)
- [Google Calendar API Quickstart](https://developers.google.com/calendar/api/quickstart/python)

---

## Quick Reference: Which File to Use?

| Use Case | File | Reason |
|----------|------|--------|
| **Quick demo/prototype** | `app.py` | Simplest setup, no database |
| **Small business (1 phone)** | `ag.py` | Google Sheets tracking, follow-ups |
| **Production (multi-tenant)** | `bolt_realtime.py` | Database, fastest responses, scalable |
| **Local development** | Any + ngrok | Use ngrok_watchdog.py for auto-tunnel |
| **Production deployment** | `bolt_realtime.py` | Railway ready, monitoring included |

---

*Last updated: 2024-11-24*
*For questions or issues, check troubleshooting section or review Railway logs.*
