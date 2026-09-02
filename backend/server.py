"""
======================================================================================
PROJECT: ATHENA — Intelligent IoT Health Monitoring Ecosystem
MODULE:  Cloud Backend & Gemini AI Ingestion Server
AUTHOR:  Cloud Solutions Architect & Full-Stack AI Developer
======================================================================================
"""

import os
import sys
import json
import time
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

# Load environment variables
load_dotenv()

# Setup Structured Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AthenaBackend")

# Configuration
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "broker.hivemq.com")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TOPIC_TELEMETRY = os.getenv("MQTT_TOPIC_TELEMETRY", "athena/device/+/telemetry")
MQTT_TOPIC_STATUS = os.getenv("MQTT_TOPIC_STATUS", "athena/device/+/status")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
AI_ROUTINE_INTERVAL_SEC = int(os.getenv("AI_ROUTINE_INTERVAL_SEC", "300"))
AI_ANOMALY_COOLDOWN_SEC = int(os.getenv("AI_ANOMALY_COOLDOWN_SEC", "45"))

# Initialize Gemini AI Client
gemini_client = None
gemini_sdk_mode = None

if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    try:
        # Try new Google GenAI SDK
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        gemini_sdk_mode = "google-genai"
        logger.info("[AI] Initialized Google GenAI SDK successfully.")
    except Exception as e1:
        try:
            # Fallback to google.generativeai SDK
            import google.generativeai as genai_legacy
            genai_legacy.configure(api_key=GEMINI_API_KEY)
            gemini_client = genai_legacy.GenerativeModel(GEMINI_MODEL)
            gemini_sdk_mode = "google-generativeai"
            logger.info("[AI] Initialized legacy google.generativeai SDK successfully.")
        except Exception as e2:
            logger.warning(f"[AI] Could not initialize Gemini SDK ({e1} / {e2}). Rule-based fallback active.")
else:
    logger.warning("[AI] GEMINI_API_KEY not set. Using built-in clinical rule engine.")


# ======================================================================================
# DATA MODELS & STATE STORAGE
# ======================================================================================

class TelemetryPayload(BaseModel):
    device_id: str = "PHC-0001"
    seq: Optional[int] = 0
    ambient_temp_c: float = 26.5
    ambient_humidity: float = 55.0
    pressure_hpa: float = 1013.2
    heat_index_c: float = 27.2
    heart_rate: int = 72
    spo2: int = 98
    finger_detected: bool = True
    is_moving: bool = False
    last_movement_min: float = 0.5
    fall_detected: bool = False
    accel_magnitude: Optional[float] = 1.0
    risk_level: int = 0
    is_emergency: Optional[bool] = False
    rssi: Optional[int] = -65
    timestamp: Optional[str] = None


class AIAdvisoryResult(BaseModel):
    risk_level: str = "NORMAL" # NORMAL, WATCH, ALERT, EMERGENCY
    summary: str
    actionable_advice: str
    clinical_assessment: str
    vital_flags: List[str] = []
    generated_at: str
    trigger_reason: str
    is_ai_generated: bool = True


class DeviceState:
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.status = "online"
        self.last_seen: float = time.time()
        self.latest_telemetry: Optional[Dict[str, Any]] = None
        self.telemetry_history: List[Dict[str, Any]] = []
        self.max_history_length = 300
        self.last_ai_routine_time: float = 0.0
        self.last_ai_anomaly_time: float = 0.0
        self.latest_advisory: Optional[Dict[str, Any]] = None

    def add_telemetry(self, data: Dict[str, Any]):
        self.last_seen = time.time()
        self.latest_telemetry = data
        self.telemetry_history.append(data)
        if len(self.telemetry_history) > self.max_history_length:
            self.telemetry_history.pop(0)


class DeviceRegistry:
    def __init__(self):
        self.devices: Dict[str, DeviceState] = {}

    def get_or_create(self, device_id: str) -> DeviceState:
        if device_id not in self.devices:
            self.devices[device_id] = DeviceState(device_id)
            logger.info(f"[REGISTRY] Registered new device: {device_id}")
        return self.devices[device_id]


registry = DeviceRegistry()


# ======================================================================================
# WEBSOCKET CONNECTION MANAGER
# ======================================================================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WS] Client connected. Total active clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"[WS] Client disconnected. Total active clients: {len(self.active_connections)}")

    async def broadcast_json(self, message: Dict[str, Any]):
        if not self.active_connections:
            return
        
        # Broadcast concurrently to all connected clients
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)


ws_manager = ConnectionManager()
loop_ref: Optional[asyncio.AbstractEventLoop] = None


# ======================================================================================
# GEMINI AI CLINICAL ADVISORY ENGINE
# ======================================================================================

def compute_rolling_stats(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not history:
        return {}
    
    valid_hr = [d.get("heart_rate", 0) for d in history if d.get("finger_detected") and d.get("heart_rate", 0) > 0]
    valid_spo2 = [d.get("spo2", 0) for d in history if d.get("finger_detected") and d.get("spo2", 0) > 0]
    heat_indices = [d.get("heat_index_c", 0.0) for d in history]
    
    return {
        "avg_heart_rate": round(sum(valid_hr) / len(valid_hr), 1) if valid_hr else None,
        "min_spo2": min(valid_spo2) if valid_spo2 else None,
        "max_heat_index_c": round(max(heat_indices), 1) if heat_indices else None,
        "sample_count": len(history)
    }


def generate_rule_based_fallback(telemetry: Dict[str, Any], trigger_reason: str) -> Dict[str, Any]:
    """Clinically grounded fallback algorithm if Gemini API is unreachable."""
    hr = telemetry.get("heart_rate", 0)
    spo2 = telemetry.get("spo2", 0)
    hi = telemetry.get("heat_index_c", 25.0)
    fall = telemetry.get("fall_detected", False)
    still_min = telemetry.get("last_movement_min", 0.0)
    finger = telemetry.get("finger_detected", False)

    risk_level = "NORMAL"
    vital_flags = []
    summary = "Patient vitals and environmental metrics are within safe physiological limits."
    advice = "Continue regular daily activities and maintain adequate hydration."
    clinical = "No immediate clinical hazards detected. Baseline cardiopulmonary and environmental balance observed."

    if fall:
        risk_level = "EMERGENCY"
        vital_flags.append("HIGH_G_FALL_IMPACT")
        vital_flags.append("PROLONGED_STILLNESS")
        summary = "CRITICAL: Patient fall detected with confirmed post-impact stillness."
        advice = "Immediate physical checkup required. Verify responsiveness, airway, and check for trauma or fractures."
        clinical = "Acute trauma indicator: Rapid deceleration followed by prolonged lack of kinetic recovery."
    elif finger and spo2 > 0 and spo2 < 90:
        risk_level = "EMERGENCY"
        vital_flags.append("SEVERE_HYPOXIA")
        summary = f"CRITICAL: Severe blood oxygen desaturation ({spo2}% SpO2)."
        advice = "Administer supplemental oxygen if prescribed and seek immediate emergency medical care."
        clinical = "Hypoxemic respiratory compromise. Immediate clinical intervention indicated."
    elif hi > 40.0:
        risk_level = "EMERGENCY"
        vital_flags.append("DANGEROUS_HEAT_INDEX")
        summary = f"Severe thermal stress detected. Ambient Heat Index is {hi:.1f}°C."
        advice = "Move patient to an air-conditioned room immediately, apply cool wet towels, and offer electrolyte fluids."
        clinical = "High risk of Heat Stroke / Heat Exhaustion exacerbated by ambient thermal load."
    elif finger and spo2 > 0 and spo2 < 93:
        risk_level = "ALERT"
        vital_flags.append("MODERATE_HYPOXIA")
        summary = f"Oxygen saturation has dropped to {spo2}%."
        advice = "Encourage deep pursed-lip breathing, ensure proper posture, and re-check pulse oximeter positioning."
        clinical = "Sub-optimal peripheral perfusion and oxygenation. Monitor for respiratory fatigue."
    elif hi > 37.0 and hr > 100:
        risk_level = "ALERT"
        vital_flags.append("HEAT_INDUCED_TACHYCARDIA")
        summary = f"Elevated heart rate ({hr} BPM) combined with high heat index ({hi:.1f}°C)."
        advice = "Patient is experiencing heat strain. Rest in shade and hydrate with cool water."
        clinical = "Compensatory cardiovascular strain due to peripheral vasodilation under heat stress."
    elif hr > 120 and still_min > 5.0:
        risk_level = "ALERT"
        vital_flags.append("RESTING_TACHYCARDIA")
        summary = f"Elevated resting heart rate ({hr} BPM) while stationary for {still_min:.1f} minutes."
        advice = "Instruct patient to sit quietly, relax, avoid stimulants, and re-assess in 5 minutes."
        clinical = "Unexplained resting tachycardia. Potential triggers: stress, fever, dehydration, or arrhythmia."
    elif hi > 35.0 or (hr > 100):
        risk_level = "WATCH"
        vital_flags.append("MILD_ELEVATION")
        summary = "Mild vital or environmental elevation noted."
        advice = "Monitor hydration levels and ensure comfortable ambient ventilation."
        clinical = "Minor physiological drift. Continued observation recommended."

    return {
        "risk_level": risk_level,
        "summary": summary,
        "actionable_advice": advice,
        "clinical_assessment": clinical,
        "vital_flags": vital_flags,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trigger_reason": trigger_reason,
        "is_ai_generated": False
    }


async def request_gemini_advisory(device_id: str, trigger_reason: str) -> Optional[Dict[str, Any]]:
    """Analyzes telemetry context using Google Gemini with structured JSON output."""
    dev = registry.get_or_create(device_id)
    latest = dev.latest_telemetry
    if not latest:
        return None

    history_stats = compute_rolling_stats(dev.telemetry_history)

    # Prepare Contextual Prompt for Gemini
    system_instruction = (
        "You are Dr. Athena AI, a board-certified clinical AI specialist and empathetic medical monitoring companion. "
        "Analyze the provided real-time and historical multi-sensor patient telemetry. "
        "Evaluate cardiac vitals (Heart Rate), respiratory saturation (SpO2), environmental heat stress (BME280 Heat Index, Temp, Pressure), "
        "and physical mobility/fall dynamics (MPU6050 50Hz impact & stillness tracking). "
        "You MUST respond ONLY with a valid, parseable JSON object adhering strictly to the schema provided."
    )

    prompt_payload = {
        "device_id": device_id,
        "trigger_reason": trigger_reason,
        "current_telemetry": {
            "heart_rate_bpm": latest.get("heart_rate"),
            "spo2_percent": latest.get("spo2"),
            "finger_contact": latest.get("finger_detected"),
            "ambient_temperature_c": latest.get("ambient_temp_c"),
            "ambient_humidity_percent": latest.get("ambient_humidity"),
            "barometric_pressure_hpa": latest.get("pressure_hpa"),
            "computed_heat_index_c": latest.get("heat_index_c"),
            "is_moving": latest.get("is_moving"),
            "stationary_duration_minutes": latest.get("last_movement_min"),
            "fall_detected": latest.get("fall_detected"),
            "accel_magnitude_g": latest.get("accel_magnitude")
        },
        "rolling_5min_statistics": history_stats,
        "required_json_format": {
            "risk_level": "NORMAL | WATCH | ALERT | EMERGENCY",
            "summary": "Concise 1-2 sentence overview of patient status and environmental context",
            "actionable_advice": "Immediate, step-by-step practical recommendations for the patient or caregiver",
            "clinical_assessment": "Pathophysiological rationale explaining why these vitals/ambient conditions require attention",
            "vital_flags": ["List of detected anomalies, e.g., TACHYCARDIA, HYPOXIA, HEAT_STRESS, IMPACT_FALL"]
        }
    }

    full_prompt = (
        f"{system_instruction}\n\n"
        f"PATIENT TELEMETRY DATA:\n{json.dumps(prompt_payload, indent=2)}\n\n"
        f"Return ONLY raw JSON without markdown code fences."
    )

    ai_result = None

    if gemini_client:
        candidate_models = [GEMINI_MODEL, "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.7-flash"]
        for mod in candidate_models:
            try:
                logger.info(f"[AI] Calling Gemini ({mod}) for device {device_id} [Trigger: {trigger_reason}]")
                response_text = ""
                if gemini_sdk_mode == "google-genai":
                    response = gemini_client.models.generate_content(
                        model=mod,
                        contents=full_prompt
                    )
                    response_text = response.text
                elif gemini_sdk_mode == "google-generativeai":
                    response = gemini_client.generate_content(full_prompt)
                    response_text = response.text

                # Clean response text if wrapped in ```json
                clean_text = response_text.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                if clean_text.startswith("```"):
                    clean_text = clean_text[3:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]
                clean_text = clean_text.strip()

                parsed_json = json.loads(clean_text)
                ai_result = {
                    "risk_level": parsed_json.get("risk_level", "NORMAL").upper(),
                    "summary": parsed_json.get("summary", "Patient metrics evaluated."),
                    "actionable_advice": parsed_json.get("actionable_advice", "Continue routine monitoring."),
                    "clinical_assessment": parsed_json.get("clinical_assessment", "Vitals within acceptable parameters."),
                    "vital_flags": parsed_json.get("vital_flags", []),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "trigger_reason": trigger_reason,
                    "is_ai_generated": True
                }
                logger.info(f"[AI SUCCESS] Gemini ({mod}) analysis complete: Risk={ai_result['risk_level']}")
                break
            except Exception as e:
                logger.warning(f"[AI RETRY] Gemini model {mod} failed: {e}. Trying next model...")

    if not ai_result:
        logger.info("[AI FALLBACK] Using built-in clinical rule engine.")
        ai_result = generate_rule_based_fallback(latest, trigger_reason)

    # Save to device state
    dev.latest_advisory = ai_result
    return ai_result


# ======================================================================================
# ANOMALY & ROUTINE TRIGGER DISPATCHER
# ======================================================================================

def check_and_trigger_ai(device_id: str, telemetry: Dict[str, Any]):
    """Evaluates whether to trigger an immediate anomaly analysis or scheduled routine report."""
    dev = registry.get_or_create(device_id)
    now = time.time()

    fall = telemetry.get("fall_detected", False) or telemetry.get("is_emergency", False)
    spo2 = telemetry.get("spo2", 98)
    finger = telemetry.get("finger_detected", False)
    hi = telemetry.get("heat_index_c", 25.0)
    hr = telemetry.get("heart_rate", 72)
    still_min = telemetry.get("last_movement_min", 0.0)

    # Anomaly conditions
    is_fall_anomaly = fall
    is_hypoxia_anomaly = finger and spo2 > 0 and spo2 < 92
    is_heat_strain_anomaly = hi > 38.0 and hr > 100
    is_resting_tachycardia = hr > 120 and still_min > 4.0 and finger

    is_emergency = is_fall_anomaly or is_hypoxia_anomaly or is_heat_strain_anomaly or is_resting_tachycardia

    reason = None
    if is_fall_anomaly:
        reason = "EMERGENCY_FALL_DETECTED"
    elif is_hypoxia_anomaly:
        reason = f"EMERGENCY_HYPOXIA_SPO2_{spo2}%"
    elif is_heat_strain_anomaly:
        reason = f"ALERT_HEAT_STRAIN_HI_{hi:.1f}C_HR_{hr}BPM"
    elif is_resting_tachycardia:
        reason = f"ALERT_RESTING_TACHYCARDIA_{hr}BPM"
    elif (now - dev.last_ai_routine_time) >= AI_ROUTINE_INTERVAL_SEC:
        reason = "ROUTINE_HEALTH_AUDIT"

    if not reason:
        return

    # Check cooldown for anomaly triggers
    if is_emergency:
        if (now - dev.last_ai_anomaly_time) < AI_ANOMALY_COOLDOWN_SEC:
            return
        dev.last_ai_anomaly_time = now
    else:
        dev.last_ai_routine_time = now

    # Execute async task in loop
    if loop_ref and loop_ref.is_running():
        asyncio.run_coroutine_threadsafe(execute_ai_pipeline(device_id, reason), loop_ref)


async def execute_ai_pipeline(device_id: str, reason: str):
    advisory = await request_gemini_advisory(device_id, reason)
    if advisory:
        # Broadcast advisory update over WebSockets
        await ws_manager.broadcast_json({
            "type": "AI_ADVISORY",
            "device_id": device_id,
            "advisory": advisory
        })


# ======================================================================================
# MQTT INGESTION SERVICE
# ======================================================================================

def on_mqtt_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info(f"[MQTT] Connected to broker: {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
        client.subscribe([(MQTT_TOPIC_TELEMETRY, 0), (MQTT_TOPIC_STATUS, 0)])
        logger.info(f"[MQTT] Subscribed to {MQTT_TOPIC_TELEMETRY} and {MQTT_TOPIC_STATUS}")
    else:
        logger.error(f"[MQTT] Connection failed with code {rc}")


def on_mqtt_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload_str = msg.payload.decode("utf-8")
        data = json.loads(payload_str)
        
        # Extract device ID from topic or payload
        topic_parts = topic.split("/")
        device_id = topic_parts[2] if len(topic_parts) >= 3 else data.get("device_id", "PHC-0001")
        data["device_id"] = device_id
        
        if "timestamp" not in data or not data["timestamp"]:
            data["timestamp"] = datetime.now(timezone.utc).isoformat()

        if topic.endswith("/status"):
            dev = registry.get_or_create(device_id)
            dev.status = data.get("status", "unknown")
            logger.info(f"[DEVICE STATUS] {device_id} is now {dev.status}")
            if loop_ref and loop_ref.is_running():
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast_json({
                        "type": "DEVICE_STATUS",
                        "device_id": device_id,
                        "status": dev.status
                    }),
                    loop_ref
                )
            return

        # Store telemetry
        dev = registry.get_or_create(device_id)
        dev.add_telemetry(data)

        # Broadcast telemetry to web clients in real time
        if loop_ref and loop_ref.is_running():
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast_json({
                    "type": "TELEMETRY",
                    "device_id": device_id,
                    "data": data,
                    "telemetry": data
                }),
                loop_ref
            )

        # Evaluate AI Trigger Rules
        check_and_trigger_ai(device_id, data)

    except Exception as e:
        logger.error(f"[MQTT ERROR] Failed processing message: {e}")


mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"Athena-Server-{int(time.time())}")
mqtt_client.on_connect = on_mqtt_connect
mqtt_client.on_message = on_mqtt_message

if MQTT_USERNAME:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

# Enable TLS when using HiveMQ Cloud or port 8883
if MQTT_BROKER_PORT == 8883 or "hivemq.cloud" in MQTT_BROKER_HOST:
    import ssl
    try:
        mqtt_client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
        logger.info("[MQTT] Configured TLS v1.2/1.3 for secure HiveMQ Cloud connection.")
    except Exception as e:
        logger.warning(f"[MQTT] TLS configuration note: {e}")


# ======================================================================================
# FASTAPI APPLICATION & LIFESPAN
# ======================================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop_ref
    loop_ref = asyncio.get_running_loop()
    
    # Start MQTT background loop
    try:
        logger.info(f"[MQTT] Initiating connection to {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}...")
        mqtt_client.connect_async(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        logger.error(f"[MQTT ERROR] Could not connect to MQTT broker: {e}")

    # Seed initial mock data so dashboard is interactive immediately
    seed_dev = registry.get_or_create("PHC-0001")
    initial_packet = {
        "device_id": "PHC-0001",
        "seq": 1,
        "ambient_temp_c": 26.8,
        "ambient_humidity": 52.0,
        "pressure_hpa": 1012.8,
        "heat_index_c": 27.5,
        "heart_rate": 74,
        "spo2": 98,
        "finger_detected": True,
        "is_moving": True,
        "last_movement_min": 0.1,
        "fall_detected": False,
        "accel_magnitude": 1.02,
        "risk_level": 0,
        "is_emergency": False,
        "rssi": -62,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    seed_dev.add_telemetry(initial_packet)
    seed_dev.latest_advisory = generate_rule_based_fallback(initial_packet, "SYSTEM_INITIALIZATION")

    yield

    # Shutdown
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    logger.info("[SERVER] Shutdown complete.")


app = FastAPI(
    title="Athena IoT Health Ingestion & AI Advisory Server",
    version="1.0.0",
    description="End-to-end telemetry ingestion, real-time WebSocket distribution, and Google Gemini AI health companion reasoning.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ======================================================================================
# REST API ENDPOINTS
# ======================================================================================

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Athena Backend",
        "mqtt_connected": mqtt_client.is_connected(),
        "gemini_ready": gemini_client is not None,
        "gemini_model": GEMINI_MODEL,
        "active_devices": len(registry.devices),
        "active_ws_clients": len(ws_manager.active_connections),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/devices")
async def list_devices():
    return [
        {
            "device_id": dev.device_id,
            "status": dev.status,
            "last_seen": dev.last_seen,
            "latest_telemetry": dev.latest_telemetry,
            "latest_advisory": dev.latest_advisory
        }
        for dev in registry.devices.values()
    ]


@app.get("/api/device/{device_id}/latest")
async def get_latest_telemetry(device_id: str):
    if device_id not in registry.devices:
        raise HTTPException(status_code=404, detail="Device not found")
    dev = registry.devices[device_id]
    return {
        "device_id": dev.device_id,
        "status": dev.status,
        "telemetry": dev.latest_telemetry,
        "advisory": dev.latest_advisory
    }


@app.get("/api/device/{device_id}/history")
async def get_device_history(device_id: str, limit: int = 50):
    if device_id not in registry.devices:
        raise HTTPException(status_code=404, detail="Device not found")
    dev = registry.devices[device_id]
    return {
        "device_id": dev.device_id,
        "count": len(dev.telemetry_history),
        "history": dev.telemetry_history[-limit:]
    }


@app.post("/api/device/{device_id}/evaluate")
async def trigger_manual_evaluation(device_id: str, background_tasks: BackgroundTasks):
    """Manually triggers Gemini AI evaluation for a device."""
    if device_id not in registry.devices:
        raise HTTPException(status_code=404, detail="Device not found")
    
    advisory = await request_gemini_advisory(device_id, "MANUAL_USER_REQUEST")
    await ws_manager.broadcast_json({
        "type": "AI_ADVISORY",
        "device_id": device_id,
        "advisory": advisory
    })
    return {"status": "success", "advisory": advisory}


@app.post("/api/simulate")
async def simulate_telemetry_packet(payload: TelemetryPayload):
    """Allows testing normal and emergency scenarios directly without hardware."""
    data = payload.model_dump()
    data["timestamp"] = datetime.now(timezone.utc).isoformat()
    device_id = data["device_id"]
    
    dev = registry.get_or_create(device_id)
    dev.add_telemetry(data)

    # Broadcast to web dashboards
    await ws_manager.broadcast_json({
        "type": "TELEMETRY",
        "device_id": device_id,
        "data": data
    })

    # Trigger AI analysis if emergency or routine
    check_and_trigger_ai(device_id, data)

    return {"status": "simulated", "data": data}


# ======================================================================================
# WEBSOCKET REAL-TIME STREAMING ENDPOINT
# ======================================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send initial snapshot of all registered devices
        snapshot = {
            "type": "INITIAL_STATE",
            "devices": [
                {
                    "device_id": dev.device_id,
                    "status": dev.status,
                    "telemetry": dev.latest_telemetry,
                    "history": dev.telemetry_history[-30:],
                    "advisory": dev.latest_advisory
                }
                for dev in registry.devices.values()
            ]
        }
        await websocket.send_json(snapshot)

        # Keep connection open and handle incoming client commands (e.g. ping/eval)
        while True:
            raw_text = await websocket.receive_text()
            try:
                cmd = json.loads(raw_text)
                if cmd.get("action") == "PING":
                    await websocket.send_json({"type": "PONG", "timestamp": time.time()})
                elif cmd.get("action") == "TRIGGER_EVALUATION":
                    target_dev = cmd.get("device_id", "PHC-0001")
                    advisory = await request_gemini_advisory(target_dev, "WEB_CLIENT_DEMAND")
                    await ws_manager.broadcast_json({
                        "type": "AI_ADVISORY",
                        "device_id": target_dev,
                        "advisory": advisory
                    })
            except Exception as e:
                logger.warning(f"[WS CLIENT MSG ERROR] {e}")

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"[WS ERROR] {e}")
        ws_manager.disconnect(websocket)


# ======================================================================================
# STATIC FILE SERVING FOR FULL-STACK DEPLOYMENT
# ======================================================================================

frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    print(f"\n==================================================")
    print(f"  ATHENA CLOUD SERVER STARTING ON http://{HOST}:{PORT}")
    print(f"==================================================\n")
    # reload=True only for local dev — disabled in production (causes "too many open files" in Docker)
    is_dev = os.getenv("ENV", "production") == "development"
    uvicorn.run("server:app", host=HOST, port=PORT, reload=is_dev)
