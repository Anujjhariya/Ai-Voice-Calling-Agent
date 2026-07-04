"""
test_emotions.py
================
Test different emotional voices in the agent.
This lets you hear how the agent sounds with different emotions.

Run this to trigger calls with different emotional tones:
  python test_emotions.py <emotion> <lang>

Examples:
  python test_emotions.py happy en
  python test_emotions.py professional en
  python test_emotions.py excited en_male
  python test_emotions.py professional hi
"""

import requests
import sys

# Make sure this matches the port your local server is running on (usually 8000)
url = "http://127.0.0.1:8000/ivr/trigger_single_call"

# Emotional voice options for English
ENGLISH_EMOTIONS = {
    "happy": "en_happy",
    "professional": "en_professional",
    "conversational": "en",
    "excited": "en_male_excited",
}

# Emotional voice options for Hindi
HINDI_EMOTIONS = {
    "happy": "hi_happy",
    "professional": "hi_professional",
    "conversational": "hi",
    "excited": "hi_male_excited",
}

def test_emotion(emotion="happy", lang="en"):
    """
    Trigger a call with the specified emotional tone.
    
    Args:
        emotion: "happy", "professional", "conversational", "excited"
        lang: "en" (English) or "hi" (Hindi)
    """
    # Select the voice variant based on emotion
    if lang.lower().startswith("hi"):
        voice_variant = HINDI_EMOTIONS.get(emotion, "hi")
        lang_code = "hi"
        greeting = f"नमस्ते! मैं Binjwa IT Solutions से कॉल कर रहा हूँ। आप कैसे मदद चाहते हैं?"
    else:
        voice_variant = ENGLISH_EMOTIONS.get(emotion, "en")
        lang_code = "en"
        greeting = "Hello! I am calling from Binjwa IT Solutions. How can I help you today?"
    
    payload = {
        "phone": "918319688692",  # Your phone number
        "name": "Tester",
        "webhookId": f"emotion-test-{emotion}-{lang_code}",
        "lang": lang_code,
        "emotion": emotion,  # Pass emotion for agent responses too
    }
    
    print(f"\n🎭 Testing {emotion.upper()} emotion with {lang_code.upper()}")
    print(f"📞 Voice variant: {voice_variant}")
    print(f"📝 Greeting: {greeting}")
    print(f"📧 Payload: {payload}\n")
    
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        emotion = sys.argv[1]
        lang = sys.argv[2] if len(sys.argv) > 2 else "en"
        test_emotion(emotion, lang)
    else:
        # Run demo with multiple emotions
        print("=" * 60)
        print("🎭 EMOTIONAL VOICE TESTING")
        print("=" * 60)
        print("\nNo emotion specified. Usage:")
        print("  python test_emotions.py happy en")
        print("  python test_emotions.py professional en")
        print("  python test_emotions.py excited en_male")
        print("  python test_emotions.py happy hi")
        print("\nAvailable emotions: happy, professional, conversational, excited\n")
