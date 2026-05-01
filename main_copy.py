# main.py — Exotel Version
import os
import json
import base64
import asyncio
import audioop
import tempfile
import wave
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response as FastAPIResponse
from dotenv import load_dotenv
from llm import get_response
from stt import transcribe_audio
from tts import generate_pcm
from calendar_api import book_meeting

load_dotenv()
app = FastAPI()
call_history = {}

RECORD_SECONDS    = 7
CHUNK_MS          = 20
CHUNKS_TO_COLLECT = int((RECORD_SECONDS * 1000) / CHUNK_MS)  # 350 chunks
SILENCE_THRESHOLD = 300
SILENCE_CHUNKS_CUTOFF = 40


@app.get("/")
async def root():
    return {"status": "Binjwa Voice Agent running on Exotel!"}


# ──────────────────────────────────────────────────────────────
# Exotel WebSocket — raw binary audio (NO JSON wrapper)
# Exotel calls this URL directly from outbound.py's "Url" param
# ──────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def voicebot_ws(websocket: WebSocket):
    await websocket.accept()
    print("✅ Exotel WebSocket connected")

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

                # Change the greeting to be more descriptive for a cold call
                greeting = (
                    "Namaste! Main Binjwa IT Solutions se bol rahi hoon. "
                    "Kya main aapse software services ke baare mein do minute baat kar sakti hoon?"
                )
                
                # We add a 1-second delay before speaking to ensure the customer 
                # has the phone to their ear after picking up.
                await asyncio.sleep(1) 
                await say(websocket, greeting, stream_sid)

                greeting_duration = estimate_speak_time(greeting)
                print(f"⏳ Greeting takes ~{greeting_duration:.1f}s, waiting...")

                asyncio.create_task(begin_listening(greeting_duration))

            elif event == "media":
                if not is_listening or processing:
                    continue

                payload    = message["media"]["payload"]
                pcm_data   = base64.b64decode(payload)
    
                # Exotel sends 16-bit Linear PCM directly! No need to decode from ULAW.
                energy = audioop.rms(pcm_data, 2)  # RMS is better for VAD
                
                audio_chunks.append(pcm_data)  # store PCM for transcription
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
                        
                        await say(websocket, speak_text, stream_sid)
                        
                        duration = estimate_speak_time(speak_text)
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


async def say(websocket: WebSocket, text: str, stream_sid: str = "unknown"):
    try:
        print(f"\n📢 Generating Audio for: {text[:80]}...")
        audio_bytes = await generate_pcm(text)
        
        if not audio_bytes:
            print("❌ say(): No audio generated")
            return
            
        payload = base64.b64encode(audio_bytes).decode("utf-8")
        
        # Twilio expects streamSid at top level — not inside media
        msg = {
            "event":     "media",
            "streamSid": stream_sid,
            "media": {
                "payload": payload
            }
        }
            
        await websocket.send_text(json.dumps(msg))
        print(f"✅ Audio Sent ({len(audio_bytes)} bytes)")
    except Exception as e:
        print(f"❌ say(): {e}")


async def process_audio(chunks: list) -> str:
    try:
        import audioop
        
        # Join all PCM chunks
        pcm_data = b"".join(chunks)
        
        # Data is already PCM, no decoding from mulaw needed for Exotel!

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(pcm_data)
            
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, transcribe_audio, wav_path, "hi")
        os.remove(wav_path)
        return result
    except Exception as e:
        print(f"❌ Audio processing: {e}")
        import traceback; traceback.print_exc()
        return ""


def estimate_speak_time(text: str) -> float:
    words = len(text.split())
    return round((words / 3.0) + 0.3, 1)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)