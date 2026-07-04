# main_exotel.py — Exotel Voicebot WebSocket Server
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
from llm import get_response, summarize_call
from db import save_call_data
from stt import transcribe_audio
from tts_exotel import generate_pcm, generate_pcm_stream
from calendar_api import book_meeting

load_dotenv()
app = FastAPI()
call_history = {}

RECORD_SECONDS    = 15
CHUNK_MS          = 20
CHUNKS_TO_COLLECT = int((RECORD_SECONDS * 1000) / CHUNK_MS)  # 750 chunks

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
    print("⏳ Pre-generating greeting audio (PCM for Exotel)...")
    GREETING_AUDIO = await generate_pcm(GREETING_TEXT)
    if GREETING_AUDIO:
        # PCM 16-bit mono 8kHz: 2 bytes per sample, 8000 samples/sec
        GREETING_DURATION = (len(GREETING_AUDIO) / (8000 * 2)) + 0.5
        print(f"✅ Greeting cached: {len(GREETING_AUDIO)} bytes ({GREETING_DURATION:.1f}s)")
    else:
        print("❌ Failed to pre-generate greeting. Will generate on first call.")


@app.get("/")
async def root():
    return {"status": "Binjwa Voice Agent running on Exotel!"}


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
                    payload = base64.b64encode(GREETING_AUDIO).decode("utf-8")
                    msg = {
                        "event":     "media",
                        "streamSid": stream_sid,
                        "media": { "payload": payload }
                    }
                    await websocket.send_text(json.dumps(msg))
                    print(f"✅ Greeting sent INSTANTLY ({len(GREETING_AUDIO)} bytes, cached PCM)")
                    greeting_duration = GREETING_DURATION
                else:
                    audio_len = await say(websocket, GREETING_TEXT, stream_sid)
                    greeting_duration = (audio_len / (8000 * 2)) + 0.5 if audio_len else 3.0
                
                print(f"⏳ Greeting plays for ~{greeting_duration:.1f}s, then listening...")
                asyncio.create_task(begin_listening(greeting_duration))

            elif event == "media":
                if not is_listening or processing:
                    continue

                payload  = message["media"]["payload"]
                pcm_data = base64.b64decode(payload)
    
                # Exotel sends 16-bit Linear PCM directly — no mu-law decoding needed
                energy = audioop.rms(pcm_data, 2)
                
                audio_chunks.append(pcm_data)
                chunk_count += 1

                SILENCE_THRESHOLD = 300
                if energy > SILENCE_THRESHOLD:
                    speech_detected = True
                    silence_chunks = 0
                else:
                    if speech_detected:
                        silence_chunks += 1

                print(f"  📼 {chunk_count}/{CHUNKS_TO_COLLECT} [Energy: {energy}]", end="\r")

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
                            loop = asyncio.get_event_loop()
                            reply_text = await loop.run_in_executor(None, get_response, user_text, history)
                        except Exception as e:
                            print(f"❌ LLM error: {e}")
                            reply_text = "माफ़ कीजिये, network issue की वजह से समझ नहीं आया।"
                            
                        speak_text = reply_text
                        if "BOOK_MEETING:" in reply_text:
                            try:
                                parts = reply_text.split("BOOK_MEETING:")
                                speak_text = parts[0].strip()
                                tag_content = parts[1].strip()
                                tag_parts = tag_content.split(":", 1)
                                if len(tag_parts) == 2:
                                    c_name, c_time = tag_parts[0].strip(), tag_parts[1].strip()
                                    loop = asyncio.get_event_loop()
                                    booking_status = await loop.run_in_executor(None, book_meeting, c_name, c_time)
                                    print(f"📅 Booking Attempt: {booking_status}")
                            except Exception as e:
                                print(f"❌ Booking parsing error: {e}")

                        print(f"🤖 Bot reply: {reply_text}")
                        history.append({"role": "user", "content": user_text})
                        history.append({"role": "assistant", "content": reply_text})
                        call_history[call_sid] = history[-10:]
                        
                        import time
                        start_time = time.time()
                        reply_audio_len = await say(websocket, speak_text, stream_sid)
                        elapsed = time.time() - start_time
                        
                        # Calculate exact remaining playback time
                        audio_duration = (reply_audio_len / 16000.0) if reply_audio_len else 3.0
                        sleep_duration = max(0.2, audio_duration - elapsed + 0.2)
                        
                        print(f"⏱️ Audio length: {audio_duration:.1f}s | Gen time: {elapsed:.1f}s | Sleep: {sleep_duration:.1f}s")
                        
                        if "BOOK_MEETING:" in reply_text:
                            print("👋 Meeting booked! Waiting for audio to finish, then hanging up...")
                            await asyncio.sleep(sleep_duration + 0.5)
                            break
                        else:
                            asyncio.create_task(begin_listening(sleep_duration))
                    else:
                        print("🔕 No speech detected (empty transcription)")
                        asyncio.create_task(begin_listening(0.5))

            elif event == "stop":
                print(f"\n📴 Call ended")
                break

    except (WebSocketDisconnect, RuntimeError):
        print(f"\n📴 Disconnected")
    except Exception as e:
        print(f"\n❌ {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"🔚 Done: {call_sid}")
        
        # Save call data to database
        history = call_history.get(call_sid, [])
        if history and call_sid != "unknown":
            print("📝 Generating summary and saving to DB...")
            try:
                loop = asyncio.get_event_loop()
                summary = await loop.run_in_executor(None, summarize_call, history)
                
                # Exotel recording URL (if Record=true was passed in outbound.py)
                rec_url = f"https://api.exotel.com/v1/Accounts/{os.getenv('EXOTEL_SID')}/Calls/{call_sid}/Recordings"
                
                await loop.run_in_executor(None, save_call_data, call_sid, history, summary, rec_url)
            except Exception as e:
                print(f"❌ DB save error: {e}")


async def say(websocket: WebSocket, text: str, stream_sid: str = "unknown") -> int:
    """
    STREAMING TTS for Exotel — sends PCM audio chunks as they arrive from Murf.
    Returns total bytes sent.
    """
    try:
        print(f"\n📢 Streaming Audio for: {text[:80]}...")
        total_bytes = 0
        
        async for pcm_chunk in generate_pcm_stream(text):
            payload = base64.b64encode(pcm_chunk).decode("utf-8")
            msg = {
                "event":     "media",
                "streamSid": stream_sid,
                "media": { "payload": payload }
            }
            await websocket.send_text(json.dumps(msg))
            total_bytes += len(pcm_chunk)
        
        if total_bytes == 0:
            print("❌ say(): No audio generated")
        else:
            print(f"✅ Audio Streamed ({total_bytes} bytes PCM)")
        return total_bytes
    except Exception as e:
        print(f"❌ say(): {e}")
        return 0


async def process_audio(chunks: list) -> str:
    """Process PCM audio chunks from Exotel — already linear PCM, no decoding needed."""
    try:
        pcm_data = b"".join(chunks)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(pcm_data)

        size = os.path.getsize(wav_path)
        print(f"  💾 WAV: {size} bytes")
            
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, transcribe_audio, wav_path, "hi")
        os.remove(wav_path)
        return result
    except Exception as e:
        print(f"❌ Audio processing: {e}")
        import traceback; traceback.print_exc()
        return ""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
