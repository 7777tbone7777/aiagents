# CLAUDE.md

This file provides guidance to Claude Code when working with the AI Agents platform.

## Project Overview

**Bolt AI Platform** - A multi-tenant AI voice agent system that enables businesses to have AI-powered phone assistants handle customer calls 24/7.

### Current Production Stack

- **Web Framework**: FastAPI (async)
- **Voice Platform**: ElevenLabs Conversational AI (primary) or OpenAI Realtime API (fallback)
- **Telephony**: Twilio Programmable Voice + Media Streams
- **Database**: Supabase (PostgreSQL)
- **Calendar**: Google Calendar API
- **Email**: Resend
- **Deployment**: Railway (divine-reprieve service)

---

## Voice Platform Configuration

### ElevenLabs Conversational AI (Recommended)

The platform uses ElevenLabs Conversational AI for natural voice conversations with Twilio.

**Environment Variables:**
```bash
USE_ELEVENLABS_CONVERSATIONAL_AI=true
ELEVENLABS_API_KEY=your_api_key
ELEVENLABS_AGENT_ID=agent_xxx  # From ElevenLabs dashboard
```

**Critical Agent Settings** (configured via ElevenLabs API or dashboard):
- `user_input_audio_format`: `ulaw_8000` (Twilio's native format)
- `agent_output_audio_format`: `ulaw_8000` (Twilio's native format)

**Audio Flow:**
```
Twilio (ulaw_8000) → Server → ElevenLabs (ulaw_8000)
ElevenLabs (ulaw_8000) → Server → Twilio (ulaw_8000)
```
No audio conversion needed - forward directly.

### OpenAI Realtime API (Fallback)

When `USE_ELEVENLABS_CONVERSATIONAL_AI=false` or not set:

```bash
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4o-realtime-preview-2024-12-17  # Latest model
```

---

## Database Schema

### `businesses` Table
```sql
id                  UUID PRIMARY KEY
business_name       TEXT
owner_email         TEXT
industry            TEXT
agent_name          TEXT
google_calendar_id  TEXT
```

### `phone_numbers` Table
```sql
id              UUID PRIMARY KEY
business_id     UUID REFERENCES businesses(id)
phone_number    TEXT UNIQUE  -- E.164 format: +1XXXXXXXXXX
```

### `calls` Table
```sql
id              UUID PRIMARY KEY
business_id     UUID REFERENCES businesses(id)
call_sid        TEXT UNIQUE
from_number     TEXT
to_number       TEXT
status          TEXT
duration        INTEGER
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/voice/incoming` | Twilio webhook for incoming calls |
| WS | `/media-stream` | WebSocket for Twilio ↔ Voice AI |
| GET | `/health` | Health check (shows uptime, active calls) |

---

## Inbound Call Flow

```
1. Customer dials Twilio number
   ↓
2. Twilio POST → /voice/incoming
   ↓
3. Server looks up business by phone number (Supabase)
   ↓
4. Returns TwiML: <Connect><Stream url="/media-stream">
   ↓
5. WebSocket established: Twilio ↔ Server ↔ ElevenLabs
   ↓
6. Real-time voice conversation
   ↓
7. Call ends → Email notification sent
```

---

## Environment Variables

### Required
```bash
# Twilio
TWILIO_ACCOUNT_SID=ACxxx
TWILIO_AUTH_TOKEN=xxx
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX

# Database
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=xxx  # or SUPABASE_KEY

# Voice AI (choose one)
USE_ELEVENLABS_CONVERSATIONAL_AI=true
ELEVENLABS_API_KEY=xxx
ELEVENLABS_AGENT_ID=agent_xxx
# OR
OPENAI_API_KEY=sk-xxx
```

### Optional
```bash
# Email
RESEND_API_KEY=re_xxx

# Google Calendar
GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
GOOGLE_CALENDAR_EMAIL=calendar@gmail.com

# Deployment
PUBLIC_BASE_URL=https://xxx.railway.app  # Auto-detected on Railway
```

---

## Deployment (Railway)

**Service**: divine-reprieve (in divine-reprieve project)

```bash
# Deploy
railway up --service divine-reprieve

# Check logs
railway logs --service divine-reprieve

# Check health
curl https://divine-reprieve-production-5080.up.railway.app/health
```

**Twilio Webhook Configuration:**
- Voice webhook: `https://divine-reprieve-production-5080.up.railway.app/voice/incoming`

---

## ElevenLabs Agent Management

Use the API to update agent settings:

```bash
# Get agent config
curl 'https://api.elevenlabs.io/v1/convai/agents/AGENT_ID' \
  -H 'xi-api-key: YOUR_API_KEY'

# Update agent (e.g., change first message)
curl -X PATCH 'https://api.elevenlabs.io/v1/convai/agents/AGENT_ID' \
  -H 'xi-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "conversation_config": {
      "agent": {
        "first_message": "Hey, thanks for calling!"
      }
    }
  }'

# Update audio format for Twilio compatibility
curl -X PATCH 'https://api.elevenlabs.io/v1/convai/agents/AGENT_ID' \
  -H 'xi-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "conversation_config": {
      "asr": {"user_input_audio_format": "ulaw_8000"},
      "tts": {"agent_output_audio_format": "ulaw_8000"}
    }
  }'
```

---

## Troubleshooting

### Silence on inbound calls
1. Check ElevenLabs agent audio format is `ulaw_8000` (not `pcm_16000`)
2. Verify agent doesn't require dynamic variables in first_message
3. Check Railway logs for WebSocket close codes

### WebSocket closes immediately (Code 1008)
- Usually means missing dynamic variables
- Check agent's `first_message` - remove `{{variable}}` placeholders or provide defaults

### "ElevenLabs not installed" warning
- This is just for the TTS SDK (optional)
- ElevenLabs Conversational AI uses WebSocket, not the SDK

### OpenAI model deprecated
- Update `OPENAI_MODEL` to `gpt-4o-realtime-preview-2024-12-17`

---

## Key Files

- **`bolt_realtime.py`** - Main application (FastAPI)
- **`requirements.txt`** - Python dependencies

---

*Last updated: 2026-01-22*
