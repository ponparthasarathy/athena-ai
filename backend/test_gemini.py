import os
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

sample_data = {
    "device_id": "PHC-0001",
    "trigger_reason": "EMERGENCY_FALL_DETECTED",
    "current_telemetry": {
        "heart_rate_bpm": 105,
        "spo2_percent": 96,
        "finger_contact": True,
        "ambient_temperature_c": 28.2,
        "ambient_humidity_percent": 58.0,
        "barometric_pressure_hpa": 1012.4,
        "computed_heat_index_c": 29.8,
        "is_moving": False,
        "stationary_duration_minutes": 1.5,
        "fall_detected": True,
        "accel_magnitude_g": 3.1
    }
}

system_instruction = (
    "You are Dr. Athena AI, a board-certified clinical AI specialist and empathetic medical monitoring companion. "
    "Analyze the provided patient telemetry. Return ONLY a valid JSON object with keys: "
    "risk_level, summary, actionable_advice, clinical_assessment, vital_flags."
)

prompt = f"{system_instruction}\n\nDATA:\n{json.dumps(sample_data, indent=2)}\n\nReturn raw JSON only."

try:
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt
    )
    print("STATUS: SUCCESS")
    print("RESPONSE TEXT:\n", response.text)
except Exception as e:
    print("STATUS: FAILED ->", e)
