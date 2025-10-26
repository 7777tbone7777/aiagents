# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI-powered sales agent system that conducts outbound phone calls using Twilio voice APIs, OpenAI for conversational AI, and ElevenLabs for text-to-speech. The system handles live phone conversations, logs interactions to Google Sheets, and sends automated SMS/email follow-ups.

**Two Versions:**
- `app.py`: Basic version with Twilio voice, OpenAI chat, and ElevenLabs TTS
- `ag.py`: Extended version with Google Sheets logging, SMS/email follow-ups, and disposition tracking

## Architecture

### Call Flow
1. **Outbound initiation** (`/outbound`): Places a call via Twilio API with lead metadata
2. **Greeting** (`/voice`): Twilio webhook delivers initial greeting using TTS, starts speech Gather
3. **Conversation loop** (`/ai`):
   - Receives transcribed user speech from Twilio
   - Stores turn in conversation history (deque with maxlen)
   - Calls OpenAI chat completion with full conversation context
   - Generates TTS audio (ElevenLabs or Twilio Polly fallback)
   - Returns TwiML with `<Gather>` to continue listening
   - Repeats until do-not-call words detected or silence
4. **Audio streaming** (`/audio/<token>.mp3`): Serves cached ElevenLabs audio to Twilio
5. **Follow-up** (`/status` in ag.py): Status callback triggers SMS/email after call completes

### Session Management
- **In-memory store** keyed by Twilio `CallSid`
- Session structure:
  - `history`: deque of (role, text) tuples (maxlen=20 in app.py, 40 in ag.py)
  - `lead`: dict with name, company, email, phone
  - `disposition`: call outcome (e.g., "DNC" for do-not-call)
- **Not production-ready**: Sessions stored in memory, cleared on restart

### AI Integration
- **OpenAI**: Uses chat completions API with conversation history
- **System prompt** (app.py:102-119, ag.py:155-162): Defines agent personality, handling instructions
- **Do-not-call detection**: Checks user speech for opt-out keywords, immediately ends call

### TTS Strategy
- **Primary**: ElevenLabs streaming API (if `ELEVENLABS_API_KEY` set)
- **Fallback**: Twilio `<Say>` with Polly.Matthew voice
- **Caching**: Audio keyed by SHA1 hash + UUID to avoid regeneration during call

### Logging (ag.py only)
- **Google Sheets**: Appends row for each conversation turn
- **Columns**: timestamp, call_sid, lead_phone, lead_name, lead_company, lead_email, role, text, disposition, followup_link
- **Auth**: Service account JSON (inline via env var or file path)

### Follow-ups (ag.py only)
- **SMS**: Via Twilio messages API
- **Email**: SendGrid (preferred) or SMTP fallback
- Triggered by Twilio status callback when call completes

## Development Commands

### Setup
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies (basic version)
pip install flask twilio openai requests python-dotenv

# Install dependencies (extended version with Sheets + follow-ups)
pip install flask twilio openai requests python-dotenv gspread google-auth sendgrid
```

### Running
```bash
# Run basic version
python app.py

# Run extended version
python ag.py

# Expose local server with ngrok (required for Twilio webhooks)
ngrok http 5000
# Then set PUBLIC_BASE_URL env var to the ngrok https URL
```

### Testing
```bash
# Health check
curl http://localhost:5000/health

# Place test call
curl -X POST "http://localhost:5000/outbound?to=+1XXXXXXXXXX&lead_name=John&company=Acme&email=john@acme.com"
```

## Environment Variables

### Required
- `OPENAI_API_KEY`: OpenAI API key for chat completions
- `TWILIO_ACCOUNT_SID`: Twilio account identifier
- `TWILIO_AUTH_TOKEN`: Twilio auth token
- `TWILIO_NUMBER`: Your Twilio phone number (format: +1XXXXXXXXXX)
- `PUBLIC_BASE_URL`: Public HTTPS URL that Twilio can reach (ngrok URL in dev)

### Google Sheets (ag.py only, one of these required)
- `GOOGLE_SERVICE_ACCOUNT_JSON`: Inline service account JSON string
- `GOOGLE_SERVICE_ACCOUNT_FILE`: Path to service account JSON file
- `GOOGLE_SHEET_ID`: Spreadsheet ID from Google Sheets URL
- `GOOGLE_WORKSHEET_NAME`: Worksheet tab name (default: "Calls")

### Optional
- `ELEVENLABS_API_KEY`: ElevenLabs API key (falls back to Twilio `<Say>` if missing)
- `ELEVENLABS_VOICE_ID`: ElevenLabs voice ID (default: "21m00Tcm4TlvDq8ikWAM" = Rachel)
- `SENDGRID_API_KEY`: SendGrid API key for email follow-ups (ag.py)
- `FROM_EMAIL`: Sender email address
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_TLS`: SMTP fallback for email
- `OPENAI_MODEL`: OpenAI model name (default: "gpt-4o-mini")
- `AGENT_NAME`: Agent name used in conversations (default: "Ava")
- `COMPANY_NAME`: Company name (default: "XR Pay")
- `PRODUCT_PITCH`: Value proposition pitch
- `DO_NOT_CALL_WORDS`: Comma-separated opt-out keywords (default: "stop,cancel,remove,do not call,do not contact")
- `PORT`: Server port (default: 5000)

## Key Constraints

1. **Public HTTPS URL required**: Twilio webhooks require a publicly accessible HTTPS endpoint. Use ngrok in development.

2. **Session persistence**: Current implementation stores sessions in memory. For production, replace `SESSIONS` dict with Redis or database.

3. **Audio cache**: `AUDIO_CACHE` dict grows unbounded. Implement expiration/cleanup for production.

4. **Synchronous design**: All API calls (OpenAI, ElevenLabs, Twilio) are synchronous. Consider async Flask or threading for production scale.

5. **Google Sheets rate limits**: ag.py appends to Sheets on every turn. For high call volumes, batch writes or use a database.

6. **Twilio speech timeout**: Uses "auto" setting. May need tuning based on use case.

## Code Modification Notes

- **Changing conversation style**: Edit `SYSTEM_PROMPT` in app.py:102-119 or ag.py:155-162
- **Adjusting conversation length**: Modify deque `maxlen` in session initialization (app.py:89, ag.py:107)
- **Adding new webhooks**: Follow Flask route pattern with `@APP.post()` or `@APP.get()`
- **Custom disposition logic**: Add classification in `ai_reply()` or `/ai` endpoint before storing in session
- **Alternative TTS**: Replace `tts_elevenlabs()` function, maintain same byte return signature
