# ElevenLabs Conversational AI Integration Draft
# This is a DRAFT implementation for migrating from OpenAI Realtime API to ElevenLabs Conversational AI

"""
INTEGRATION APPROACH:
- Use ElevenLabs Conversational AI Platform (agent configured in dashboard)
- Bridge Twilio Media Streams → ElevenLabs WebSocket
- Remove OpenAI Realtime API dependency
- Keep all existing business logic (database, calendar, emails)

KEY CHANGES:
1. WebSocket connection to ElevenLabs instead of OpenAI
2. Different event handling (ElevenLabs events vs OpenAI events)
3. No manual response.create triggers (ElevenLabs handles turn-taking!)
4. Simpler audio handling (direct μ-law passthrough)

ENVIRONMENT VARIABLES NEEDED:
- ELEVENLABS_AGENT_ID=agt_xxxxxxxxxxxxx (from dashboard)
- ELEVENLABS_API_KEY=sk_xxxxxxxxxxxxx (from dashboard)
- Keep existing vars (SUPABASE, TWILIO, etc.)
"""

import os
import json
import asyncio
import websockets
import base64
import time
from collections import deque
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ElevenLabs Conversational AI Configuration
ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_WS_URL = f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={ELEVENLABS_AGENT_ID}"

# Existing configuration (unchanged)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# ... (all other existing env vars)

# Initialize FastAPI
app = FastAPI()

# Session storage (unchanged)
SESSIONS = {}

# Logging helper (unchanged)
def log(message):
    timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    print(f"{timestamp} {message}")

# ========================================
# ELEVENLABS WEBSOCKET HANDLER
# ========================================

async def handle_media_stream_elevenlabs(websocket: WebSocket, call_sid: str):
    """
    Main WebSocket handler for Twilio <-> ElevenLabs bridge

    Flow:
    1. Connect to ElevenLabs Conversational AI WebSocket
    2. Receive audio from Twilio, forward to ElevenLabs
    3. Receive audio from ElevenLabs, forward to Twilio
    4. Handle events and maintain session state
    """

    log(f"[ElevenLabs] Starting media stream handler for call {call_sid}")

    # Connect to ElevenLabs WebSocket
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY
    }

    try:
        async with websockets.connect(
            ELEVENLABS_WS_URL,
            extra_headers=headers,
            ping_interval=20,
            ping_timeout=10
        ) as elevenlabs_ws:

            log(f"[ElevenLabs] Connected to agent {ELEVENLABS_AGENT_ID}")

            # Session variables
            stream_sid = None
            latest_media_timestamp = 0

            async def receive_from_twilio():
                """Receive audio from Twilio and send to ElevenLabs"""
                nonlocal stream_sid, latest_media_timestamp

                try:
                    async for message in websocket.iter_text():
                        data = json.loads(message)

                        if data['event'] == 'media':
                            latest_media_timestamp = int(data['media']['timestamp'])

                            # Forward audio to ElevenLabs
                            # ElevenLabs expects base64 μ-law audio chunks
                            audio_message = {
                                "type": "audio",
                                "audio": data['media']['payload']  # Already base64 μ-law from Twilio
                            }
                            await elevenlabs_ws.send(json.dumps(audio_message))

                        elif data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            log(f"[Twilio] Stream started: {stream_sid}")

                            # Initialize ElevenLabs conversation
                            # (ElevenLabs may have a start message - TBD from docs)
                            start_message = {
                                "type": "conversation_initiation_client_data",
                                "conversation_config_override": {
                                    # Optional overrides if needed
                                }
                            }
                            await elevenlabs_ws.send(json.dumps(start_message))

                        elif data['event'] == 'stop':
                            log(f"[Twilio] Stream stopped: {stream_sid}")
                            # Send stop to ElevenLabs
                            await elevenlabs_ws.send(json.dumps({"type": "end_conversation"}))
                            break

                except Exception as e:
                    log(f"[Error] Twilio receive error: {e}")

            async def receive_from_elevenlabs():
                """Receive audio/events from ElevenLabs and send to Twilio"""
                try:
                    async for message in elevenlabs_ws:
                        response = json.loads(message)

                        # Handle different event types
                        event_type = response.get('type')

                        if event_type == 'audio':
                            # ElevenLabs sends audio response
                            audio_base64 = response.get('audio')

                            # Forward to Twilio
                            twilio_message = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": audio_base64
                                }
                            }
                            await websocket.send_text(json.dumps(twilio_message))

                        elif event_type == 'transcript':
                            # User or agent transcript
                            transcript_text = response.get('text')
                            role = response.get('role')  # 'user' or 'agent'

                            log(f"[Transcript] {role}: {transcript_text}")

                            # Save to database
                            session = SESSIONS.get(call_sid, {})
                            if session:
                                # Save transcript using existing function
                                # save_transcript(call_id, role, transcript_text)
                                pass

                        elif event_type == 'conversation_initiation_metadata':
                            # Conversation started
                            log(f"[ElevenLabs] Conversation initiated")

                        elif event_type == 'error':
                            log(f"[ElevenLabs Error] {response.get('message')}")

                        else:
                            log(f"[ElevenLabs] Unknown event: {event_type}")

                except websockets.exceptions.ConnectionClosed:
                    log("[ElevenLabs] WebSocket closed")
                except Exception as e:
                    log(f"[Error] ElevenLabs receive error: {e}")

            # Run both streams concurrently
            await asyncio.gather(
                receive_from_twilio(),
                receive_from_elevenlabs()
            )

    except Exception as e:
        log(f"[Error] WebSocket connection failed: {e}")
    finally:
        log(f"[ElevenLabs] Handler complete for call {call_sid}")

# ========================================
# TWILIO WEBHOOK ENDPOINTS (Keep existing)
# ========================================

@app.post("/inbound")
async def handle_inbound_call(request: Request):
    """
    Twilio webhook for incoming calls
    Same as before - just returns TwiML to start Media Stream
    """
    # ... (keep existing code)
    pass

@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """
    WebSocket endpoint for Twilio Media Streams
    Now connects to ElevenLabs instead of OpenAI
    """
    await websocket.accept()

    # Get call SID from query params or first message
    call_sid = None

    # Wait for first message to get call_sid
    first_message = await websocket.receive_text()
    data = json.loads(first_message)

    if data['event'] == 'start':
        call_sid = data['start']['customParameters'].get('CallSid')

    if not call_sid:
        log("[Error] No call_sid found")
        await websocket.close()
        return

    # Handle the media stream with ElevenLabs
    await handle_media_stream_elevenlabs(websocket, call_sid)

# ========================================
# NOTES FOR COMPLETION:
# ========================================

"""
TODO BEFORE DEPLOYMENT:
1. Verify ElevenLabs WebSocket message formats from official docs
2. Add proper error handling for all scenarios
3. Keep all existing database functions (unchanged)
4. Keep all existing calendar functions (unchanged)
5. Keep all existing email functions (unchanged)
6. Add function calling if ElevenLabs supports it (tools/actions)
7. Test with real Twilio call
8. Update requirements.txt if needed (elevenlabs package)
9. Update environment variable documentation

ADVANTAGES OF THIS APPROACH:
- No more VAD issues! ElevenLabs handles turn-taking
- No more manual response.create triggers
- Better voice quality (already using ElevenLabs)
- LLM flexibility (can switch in dashboard)
- Simpler codebase (less event handling complexity)

QUESTIONS TO VERIFY:
- Exact format of audio messages (audio chunks)
- How to get transcripts in real-time
- Function calling / tool integration
- Session configuration options
- Error event formats
"""
