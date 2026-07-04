"""
vad.py — Voice Activity Detection (silence detection)
======================================================
Kaam: Live audio chunks mein detect karna ki customer ne bolna
      band kar diya hai — taaki hum turant STT trigger kar sakein.

Purane system mein Vobiz ka <Record timeout="1"> yeh karta tha (1 sec fixed).
Ab hum khud karte hain — 500-600ms mein hi pata chal jata hai.

Energy-based VAD hai — koi ML model nahi, zero latency, telephony ke liye kaafi hai.
"""

import struct


class SilenceDetector:
    """
    Har incoming audio chunk pe feed() call karo.
    Jab return value True ho — customer ne bolna band kiya, ab process karo.

    Usage:
        vad = SilenceDetector()
        ...
        is_turn_complete = vad.feed(pcm16_chunk)
        if is_turn_complete:
            utterance = vad.get_and_reset_buffer()
            # → STT → LLM → TTS
    """

    def __init__(
        self,
        sample_rate: int = 8000,
        silence_threshold: int = 500,     # energy level — isse niche = silence (tune karna pad sakta hai)
        silence_duration_ms: int = 600,   # itni der silence = turn complete
        min_speech_ms: int = 300,         # itna bola hi nahi toh noise hai, ignore karo
    ):
        self.sample_rate = sample_rate
        self.silence_threshold = silence_threshold
        self.silence_needed_ms = silence_duration_ms
        self.min_speech_ms = min_speech_ms

        self._buffer = bytearray()
        self._silence_ms = 0.0
        self._speech_ms = 0.0
        self._speaking = False

    def feed(self, pcm16_chunk: bytes) -> bool:
        """
        PCM 16-bit mono audio chunk do.
        Return True = customer ka turn complete (speech thi + ab silence hai).
        """
        chunk_ms = (len(pcm16_chunk) / 2) / self.sample_rate * 1000
        energy = self._rms(pcm16_chunk)

        self._buffer.extend(pcm16_chunk)

        if energy > self.silence_threshold:
            # Customer bol raha hai
            self._speaking = True
            self._speech_ms += chunk_ms
            self._silence_ms = 0.0
        else:
            # Silence chal rahi hai
            if self._speaking:
                self._silence_ms += chunk_ms

        # Turn complete: bola tha (min se zyada) + ab kaafi der se chup hai
        if (
            self._speaking
            and self._speech_ms >= self.min_speech_ms
            and self._silence_ms >= self.silence_needed_ms
        ):
            return True

        # Buffer safety — 30 sec se zyada mat rakho (memory)
        max_bytes = self.sample_rate * 2 * 30
        if len(self._buffer) > max_bytes:
            del self._buffer[: len(self._buffer) - max_bytes]

        return False

    def is_user_speaking(self) -> bool:
        """Barge-in ke liye — kya customer ABHI bol raha hai?"""
        return self._speaking and self._silence_ms < 200

    def get_and_reset_buffer(self) -> bytes:
        """Turn complete hone pe — poori utterance lo aur reset karo."""
        data = bytes(self._buffer)
        self._buffer.clear()
        self._silence_ms = 0.0
        self._speech_ms = 0.0
        self._speaking = False
        return data

    @staticmethod
    def _rms(pcm16: bytes) -> float:
        """Root-mean-square energy — kitni loud awaaz hai."""
        count = len(pcm16) // 2
        if count == 0:
            return 0.0
        samples = struct.unpack(f"<{count}h", pcm16[: count * 2])
        sum_sq = sum(s * s for s in samples)
        return (sum_sq / count) ** 0.5


# ─────────────────────────────────────────────
# Audio format conversion helpers
# Telephony (Vobiz) mulaw 8kHz bhejta hai,
# Whisper/Murf PCM16 WAV samajhte hain.
# ─────────────────────────────────────────────

# Python 3.13+ mein audioop hata diya gaya hai — audioop-lts install karo:
#   pip install audioop-lts
try:
    import audioop
except ImportError:
    import audioop_lts as audioop


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Vobiz se aaya mulaw audio → PCM16 (VAD + Whisper ke liye)."""
    return audioop.ulaw2lin(mulaw_bytes, 2)


def pcm16_to_mulaw(pcm16_bytes: bytes) -> bytes:
    """Murf ka PCM16 audio → mulaw (Vobiz ko wapas bhejne ke liye)."""
    return audioop.lin2ulaw(pcm16_bytes, 2)


def pcm16_to_wav(pcm16_bytes: bytes, sample_rate: int = 8000) -> bytes:
    """PCM16 raw bytes ko WAV file format mein wrap karo (Whisper ke liye)."""
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16_bytes)
    return buf.getvalue()
