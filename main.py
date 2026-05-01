# import os
# import tempfile
# import httpx
# from fastapi import FastAPI, Request, Response
# from fastapi.responses import FileResponse
# from dotenv import load_dotenv
# import asyncio
# # Optimized engines
# from stt import transcribe_audio
# from llm import get_response
# from tts import stream_voice
# from lang_detect import detect_language
# from calendar_api import book_meeting

# load_dotenv()
# app = FastAPI()
# call_history = {}
# BASE_URL = os.getenv("BASE_URL")

# @app.get("/")
# async def read_root():
#     return {"message": "Exotel AI Voice Agent is running!"}

# # ─────────────────────────────────────────────
# # ROUTE 1: Incoming call — greet the user
# # ─────────────────────────────────────────────
# # @app.get("/answer")
# # @app.post("/answer")
# # async def answer_call():
# #     """Exotel Passthru hits this URL when a call connects."""
# #     # Note: Exotel Passthru typically handles the 'Say' or 'Play' 
# #     # via their Flow Builder, but if you use custom XML, use this:
# #     response_xml = f"""
# #     <Response>
# #         <Say>Namaste! Main aapki kaise madad kar sakta hoon?</Say>
# #         <Record action="{BASE_URL}/process_speech" method="POST" maxLength="10" timeout="3" />
# #     </Response>
# #     """
# #     return Response(content=response_xml, media_type="text/xml")


# @app.get("/answer")
# @app.post("/answer")
# async def answer_call():
#     # Adding the <?xml?> header ensures strict compatibility
#     response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
#     <Response>
#         <Say>Namaste! Binjwa IT Solutions mein aapka swagat hai. Kripya bataiye main aapki kya madad kar sakta hoon?</Say>
#         <Record action="{BASE_URL}/process_speech" method="POST" maxLength="10" timeout="5" playBeep="true" transcribe="false" />
#     </Response>
#     """
#     return Response(content=response_xml, media_type="application/xml")



# # ─────────────────────────────────────────────
# # ROUTE 2: Process the recorded speech
# # ─────────────────────────────────────────────
# @app.get("/process_speech")
# @app.post("/process_speech")
# async def process_speech(request: Request):
#     print("--- Incoming Recording Received ---")
#     form_data = await request.form()
#     # 1. DEFINE call_sid FIRST
#     call_sid = form_data.get("CallSid", "unknown")
#     recording_url = form_data.get("RecordingUrl", "")

#     # 2. Add your delay if needed
#     await asyncio.sleep(1)
    
#     # recording_url = form_data.get("RecordingUrl", "")
#     if not recording_url:
#         return await retry_logic()

#     # Wait and Retry Logic to handle Exotel's file-saving delay
#     async with httpx.AsyncClient(follow_redirects=True) as client:
#         auth = (os.getenv("EXOTEL_API_KEY"), os.getenv("EXOTEL_API_TOKEN"))
        
#         audio_resp = None
#         for attempt in range(3):  # Try 3 times
#             audio_resp = await client.get(recording_url, auth=auth)
#             if audio_resp.status_code == 200:
#                 break
#             print(f"Attempt {attempt + 1} failed (404), waiting...")
#             await asyncio.sleep(1.5) # Give Exotel 1.5 seconds to save the file
            
#     if not audio_resp or audio_resp.status_code != 200:
#         print(f"Final download failure: {audio_resp.status_code if audio_resp else 'No Response'}")
#         return await retry_logic()

#     with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
#         tmp.write(audio_resp.content)
#         audio_path = tmp.name

#     # 2. STT (Groq Whisper Turbo)
#     try:
#         user_text = transcribe_audio(audio_path, language="hi")
#     except Exception as e:
#         print(f"STT error: {e}")
#         return await retry_logic()
#         # user_text = ""

#     if not user_text.strip():
#         return await retry_logic()

#     # 3. Detect Language & Get LLM Response
#     lang_info = detect_language(user_text)
#     history = call_history.get(call_sid, [])
    
#     try:
#         reply_text = get_response(user_text, history)
#     except Exception as e:
#         print(f"LLM error: {e}")
#         reply_text = "Maafi chahta hoon, server mein thodi takleef hai."

#     # 4. Check for meeting booking
#     if "BOOK_MEETING:" in reply_text:
#         try:
#             # parts = reply_text.split(":")
#             # name, dt_str = parts[1].strip(), f"{parts[2].strip()}:{parts[3].strip()}"
            
#             # ✅ Fix — split only on first 2 colons
#             _, name, datetime_str = reply_text.split(":", 2)
#             name = name.strip()
#             dt_str = datetime_str.strip()
            
#             reply_text = book_meeting(name, dt_str)
#         except Exception as e:
#             print(f"Booking error: {e}")

#     # 5. Update History
#     history.append({"role": "user", "content": user_text})
#     history.append({"role": "assistant", "content": reply_text})
#     call_history[call_sid] = history[-10:]

#     # 6. Optimized TTS (Stream bytes directly to temporary file)
#     audio_filename = f"reply_{call_sid}.mp3"
#     audio_path = os.path.join(tempfile.gettempdir(), audio_filename)
    
#     # with open(audio_path, "wb") as f:
#     #     async for chunk in stream_voice(reply_text, lang_info["groq_lang"]):
#     #         f.write(chunk)


#     with open(audio_path, "wb") as f:
#         async for chunk in stream_voice(reply_text, lang_info["groq_lang"]):
#             f.write(chunk)

#     if os.path.getsize(audio_path) == 0:
#         print("TTS error: empty audio file generated")
#         return await retry_logic()


#     # 7. Final Exotel XML Response
#     exotel_resp = f"""
#     <Response>
#         <Play>{BASE_URL}/audio/{audio_filename}</Play>
#         <Record action="{BASE_URL}/process_speech" method="POST" maxLength="10" timeout="3" />
#     </Response>
#     """
#     return Response(content=exotel_resp, media_type="application/xml")

# @app.get("/audio/{filename}")
# async def serve_audio(filename: str):
#     path = os.path.join(tempfile.gettempdir(), filename)
#     if os.path.exists(path):
#         return FileResponse(path, media_type="audio/mpeg")
#     return Response(content="File not found", status_code=404)

# async def retry_logic():
#     resp_xml = f"""
#     <Response>
#         <Say>Kripya dobara bolein.</Say>
#         <Record action="{BASE_URL}/process_speech" method="POST" maxLength="10" timeout="3" />
#     </Response>
#     """
#     return Response(content=resp_xml, media_type="application/xml")

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)









import os
import json
import base64
import asyncio
import audioop
import tempfile
import wave
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from llm import get_response
from lang_detect import detect_language
from stt import transcribe_audio
from tts import generate_pcm, generate_pcm_stream
from calendar_api import book_meeting

load_dotenv()
app = FastAPI()
call_history = {}

RECORD_SECONDS    = 7
CHUNK_MS          = 20
CHUNKS_TO_COLLECT = int((RECORD_SECONDS * 1000) / CHUNK_MS)  # 350 chunks

# ── Pre-cached greeting audio (generated once at startup) ──
GREETING_TEXT = (
    "नमस्ते! मैं Binjwa IT Solutions से बोल रही हूँ। "
    "क्या मैं आपसे software services के बारे में दो मिनट बात कर सकती हूँ?"
)
GREETING_AUDIO: bytes = b""   # filled by startup event
GREETING_DURATION: float = 9.0  # default fallback

@app.on_event("startup")
async def preload_greeting():
    """Generate greeting audio once at server boot so calls start instantly."""
    global GREETING_AUDIO, GREETING_DURATION
    print("⏳ Pre-generating greeting audio...")
    GREETING_AUDIO = await generate_pcm(GREETING_TEXT)
    if GREETING_AUDIO:
        GREETING_DURATION = (len(GREETING_AUDIO) / 8000.0) + 0.5
        print(f"✅ Greeting cached: {len(GREETING_AUDIO)} bytes ({GREETING_DURATION:.1f}s)")
    else:
        print("❌ Failed to pre-generate greeting. Will generate on first call.")


@app.get("/")
async def root():
    return {"status": "Binjwa Voice Agent running!"}

from fastapi.responses import Response as FastAPIResponse

@app.get("/twiml")
@app.post("/twiml")
async def twiml_answer():
    """
    Twilio hits this HTTP endpoint first when a call comes in.
    We tell Twilio: 'connect this call to our WebSocket server'
    """
    BASE_URL = os.getenv("BASE_URL", "")
    # Convert https:// to wss:// for WebSocket
    ws_url = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}/ws">
            <Parameter name="source" value="twilio"/>
        </Stream>
    </Connect>
</Response>"""
    return FastAPIResponse(content=xml, media_type="application/xml")

@app.websocket("/ws")
async def voicebot_ws(websocket: WebSocket):
    await websocket.accept()
    print("✅ WebSocket connected")

    call_sid     = "unknown"
    stream_sid   = "unknown"
    audio_chunks = []
    is_listening = False
    processing   = False
    chunk_count  = 0
    silence_chunks = 0
    speech_detected = False

    async def begin_listening(duration: float):
        nonlocal is_listening, audio_chunks, chunk_count, silence_chunks, speech_detected, processing
        # Wait for greeting/reply to finish before opening the mic
        await asyncio.sleep(duration)
        audio_chunks  = []
        chunk_count   = 0
        silence_chunks = 0
        speech_detected = False
        is_listening  = True
        processing    = False
        print(f"\n🎙️ NOW recording user (up to {RECORD_SECONDS}s) — SPEAK NOW!")

    try:
        while True:
            data    = await websocket.receive_text()
            message = json.loads(data)
            event   = message.get("event", "")

            if event != "media":
                print(f"\n📩 {event} | {json.dumps(message)[:200]}")

            if event == "connected":
                print("🔗 Connected")

            elif event == "start":
                start_data = message.get("start", {})
                call_sid   = start_data.get("call_sid") or start_data.get("callSid") or "unknown"
                stream_sid = start_data.get("stream_sid") or start_data.get("streamSid") or message.get("stream_sid") or "unknown"
                print(f"📞 Outbound Call Connected: {call_sid} (Stream: {stream_sid})")

                # Use pre-cached greeting audio for instant playback
                if GREETING_AUDIO:
                    # Send cached audio directly — no TTS wait!
                    payload = base64.b64encode(GREETING_AUDIO).decode("utf-8")
                    msg = {
                        "event":     "media",
                        "streamSid": stream_sid,
                        "media": { "payload": payload }
                    }
                    await websocket.send_text(json.dumps(msg))
                    print(f"✅ Greeting sent INSTANTLY ({len(GREETING_AUDIO)} bytes, cached)")
                    greeting_duration = GREETING_DURATION
                else:
                    # Fallback: generate on the fly (only if startup failed)
                    audio_len = await say(websocket, GREETING_TEXT, stream_sid)
                    greeting_duration = (audio_len / 8000.0) + 0.5 if audio_len else 3.0
                
                print(f"⏳ Greeting plays for ~{greeting_duration:.1f}s, then listening...")
                asyncio.create_task(begin_listening(greeting_duration))

            elif event == "media":
                if not is_listening or processing:
                    continue

                payload    = message["media"]["payload"]
                mulaw_data = base64.b64decode(payload)
    
                # Decode mulaw → PCM for VAD energy calculation
                pcm_for_vad = audioop.ulaw2lin(mulaw_data, 2)
                energy = audioop.rms(pcm_for_vad, 2)  # RMS is better for VAD
                
                audio_chunks.append(mulaw_data)  # store mulaw for transcription
                chunk_count += 1

                SILENCE_THRESHOLD = 300  # RMS threshold for speech detection
                if energy > SILENCE_THRESHOLD:
                    speech_detected = True
                    silence_chunks = 0
                else:
                    if speech_detected:
                        silence_chunks += 1

                print(f"  📼 {chunk_count}/{CHUNKS_TO_COLLECT} [Energy: {energy}]", end="\r")

                # Stop after 0.8s of silence after speech detected
                stop_early = speech_detected and silence_chunks > 40

                if chunk_count >= CHUNKS_TO_COLLECT or stop_early:
                    is_listening = False
                    processing = True
                    print(f"\n🔄 Processing {chunk_count} chunks...")
                    
                    user_text = await process_audio(audio_chunks)
                    print(f"👤 User said: {user_text}")
                    
                    if user_text.strip():
                        history = call_history.get(call_sid, [])
                        try:
                            # Run LLM synchronously but offload to thread
                            loop = asyncio.get_event_loop()
                            reply_text = await loop.run_in_executor(None, get_response, user_text, history)
                        except Exception as e:
                            print(f"❌ LLM error: {e}")
                            reply_text = "Maafi chahta hoon, network ki vajah se mujhe samajh nahi aaya."
                            
                        # Handle BOOK_MEETING tag if present
                        speak_text = reply_text
                        if "BOOK_MEETING:" in reply_text:
                            try:
                                # Example: "Sure! BOOK_MEETING:Anuj:2026-05-01 10:00"
                                parts = reply_text.split("BOOK_MEETING:")
                                speak_text = parts[0].strip()  # Text to speak
                                
                                tag_content = parts[1].strip()
                                tag_parts = tag_content.split(":", 1)
                                if len(tag_parts) == 2:
                                    c_name, c_time = tag_parts[0].strip(), tag_parts[1].strip()
                                    # Run book_meeting in a thread
                                    loop = asyncio.get_event_loop()
                                    booking_status = await loop.run_in_executor(None, book_meeting, c_name, c_time)
                                    print(f"📅 Booking Attempt: {booking_status}")
                            except Exception as e:
                                print(f"❌ Booking parsing error: {e}")

                        print(f"🤖 Bot reply: {reply_text}")
                        history.append({"role": "user", "content": user_text})
                        history.append({"role": "assistant", "content": reply_text})
                        call_history[call_sid] = history[-10:]
                        
                        reply_audio_len = await say(websocket, speak_text, stream_sid)
                        
                        duration = (reply_audio_len / 8000.0) + 0.5 if reply_audio_len else 3.0
                        asyncio.create_task(begin_listening(duration))
                    else:
                        print("🔕 No speech detected (empty transcription)")
                        asyncio.create_task(begin_listening(0.5))

            elif event == "stop":
                print(f"\n📴 Call ended")
                break

    except WebSocketDisconnect:
        print(f"\n📴 Disconnected")
    except Exception as e:
        print(f"\n❌ {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"🔚 Done: {call_sid}")


def estimate_speak_time(text: str) -> float:
    """
    Estimate speaking time.
    Indian speech ~3 words/second, 0.3s buffer only.
    """
    words = len(text.split())
    return round((words / 3.0) + 0.3, 1)


async def say(websocket: WebSocket, text: str, stream_sid: str = "unknown") -> int:
    """
    STREAMING TTS — sends audio to Twilio as chunks arrive from Murf.
    Caller hears audio within ~130ms. Returns total bytes sent.
    """
    try:
        print(f"\n📢 Streaming Audio for: {text[:80]}...")
        total_bytes = 0
        
        async for ulaw_chunk in generate_pcm_stream(text):
            payload = base64.b64encode(ulaw_chunk).decode("utf-8")
            msg = {
                "event":     "media",
                "streamSid": stream_sid,
                "media": { "payload": payload }
            }
            await websocket.send_text(json.dumps(msg))
            total_bytes += len(ulaw_chunk)
        
        if total_bytes == 0:
            print("❌ say(): No audio generated")
        else:
            print(f"✅ Audio Streamed ({total_bytes} bytes)")
        return total_bytes
    except Exception as e:
        print(f"❌ say(): {e}")
        return 0


async def process_audio(chunks: list) -> str:
    try:
        import audioop
        
        # Join all mulaw chunks
        mulaw_data = b"".join(chunks)
        
        # DECODE mulaw → linear PCM (this was missing before!)
        pcm_data = audioop.ulaw2lin(mulaw_data, 2)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(pcm_data)   # ← now writing real PCM

        size = os.path.getsize(wav_path)
        print(f"  💾 WAV: {size} bytes")
        
        # Run synchronous transcription in a thread
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, transcribe_audio, wav_path, "hi")
        
        # Clean up
        os.remove(wav_path)
        return result

    except Exception as e:
        print(f"❌ Audio: {e}")
        import traceback
        traceback.print_exc()
        return ""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)