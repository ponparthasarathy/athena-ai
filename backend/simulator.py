"""
======================================================================================
PROJECT: ATHENA — IoT Telemetry Simulator & Test Suite
AUTHOR:  Cloud Solutions Architect
DESCRIPTION:
  Publishes simulated telemetry over MQTT to test end-to-end cloud ingestion,
  WebSocket broadcasts, and Gemini AI trigger evaluations with various physiological states.
======================================================================================
"""

import os
import sys
import json
import time
import math
import random
from datetime import datetime, timezone
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path) if os.path.exists(env_path) else load_dotenv()

MQTT_BROKER = os.getenv("MQTT_BROKER_HOST", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("MQTT_BROKER_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USERNAME", "")
MQTT_PASS = os.getenv("MQTT_PASSWORD", "")
DEVICE_ID = os.getenv("DEVICE_ID", "PHC-0001")
TOPIC = f"athena/device/{DEVICE_ID}/telemetry"

print("\n==================================================")
print("   ATHENA IOT TELEMETRY SIMULATOR")
print(f"   Target Broker: {MQTT_BROKER}:{MQTT_PORT}")
print(f"   Target Device: {DEVICE_ID}")
print("==================================================")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"Athena-Sim-{random.randint(1000, 9999)}")
if MQTT_USER:
    client.username_pw_set(MQTT_USER, MQTT_PASS)

if MQTT_PORT == 8883 or "hivemq.cloud" in MQTT_BROKER:
    import ssl
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)

try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    print("[OK] Connected to MQTT broker successfully.")
except Exception as e:
    print(f"[ERROR] Failed to connect: {e}")
    sys.exit(1)


def compute_heat_index(t_c, rh):
    t_f = t_c * 9.0 / 5.0 + 32.0
    hi_f = (-42.379 + 2.04901523 * t_f + 10.14333127 * rh
            - 0.22475541 * t_f * rh - 0.00683783 * t_f * t_f
            - 0.05481717 * rh * rh + 0.00122874 * t_f * t_f * rh
            + 0.00085282 * t_f * rh * rh - 0.00000199 * t_f * t_f * rh * rh)
    return (hi_f - 32.0) * 5.0 / 9.0


def publish_packet(scenario_name: str, **kwargs):
    now_iso = datetime.now(timezone.utc).isoformat()
    
    t_c = kwargs.get("temp_c", 26.5 + random.uniform(-0.5, 0.5))
    rh = kwargs.get("humidity", 54.0 + random.uniform(-2.0, 2.0))
    hi = compute_heat_index(t_c, rh)

    payload = {
        "device_id": DEVICE_ID,
        "seq": kwargs.get("seq", 1),
        "ambient_temp_c": round(t_c, 2),
        "ambient_humidity": round(rh, 1),
        "pressure_hpa": round(kwargs.get("pressure", 1013.2 + random.uniform(-0.3, 0.3)), 1),
        "heat_index_c": round(hi, 2),
        "heart_rate": kwargs.get("heart_rate", 72 + random.randint(-3, 3)),
        "spo2": kwargs.get("spo2", 98),
        "finger_detected": kwargs.get("finger_detected", True),
        "is_moving": kwargs.get("is_moving", False),
        "last_movement_min": round(kwargs.get("last_movement_min", 0.5), 2),
        "fall_detected": kwargs.get("fall_detected", False),
        "accel_magnitude": round(kwargs.get("accel_mag", 1.0), 2),
        "tinyml_fall_prob": kwargs.get("tinyml_fall_prob", 0.98 if kwargs.get("fall_detected") else 0.01),
        "tinyml_class": kwargs.get("tinyml_class", "FALL_DETECTED" if kwargs.get("fall_detected") else ("WALKING" if kwargs.get("is_moving") else "RESTING")),
        "tinyml_heat_class": kwargs.get("tinyml_heat_class", "HEAT_EMERGENCY" if hi >= 41.0 else ("HEAT_WARNING" if hi >= 38.0 else ("HEAT_CAUTION" if hi >= 32.0 else "HEAT_NORMAL"))),
        "tinyml_heat_prob": kwargs.get("tinyml_heat_prob", 0.99),
        "tinyml_accuracy": kwargs.get("tinyml_accuracy", 99.6),

        "risk_level": kwargs.get("risk_level", 0),
        "is_emergency": kwargs.get("is_emergency", False),
        "rssi": -60 + random.randint(-5, 5),
        "timestamp": now_iso
    }

    msg = json.dumps(payload)
    client.publish(TOPIC, msg)
    print(f"[{scenario_name.upper()}] Sent payload -> HR: {payload['heart_rate']} bpm | SpO2: {payload['spo2']}% | TinyML Class: {payload['tinyml_class']} (Prob: {payload['tinyml_fall_prob']})")



def run_interactive():
    seq = 0
    while True:
        print("\nSelect Scenario to Emit:")
        print("1. Routine Normal Vitals (Resting)")
        print("2. Normal Active / Walking Vitals")
        print("3. EMERGENCY: High-G Fall Detected + Post-Impact Stillness")
        print("4. EMERGENCY: Severe Hypoxia (SpO2 88%)")
        print("5. ALERT: Heat Wave Stress (Temp 39°C, HR 112 BPM)")
        print("6. ALERT: Flash Flood Inundation (Barometric Drop < 1005 hPa, RH 94%)")
        print("7. ALERT: Air Pollution / Winter Smog Inversion (High Pres 1021 hPa, Humidity Inversion)")
        print("8. Continuous Live Stream (Routine every 5 seconds)")
        print("9. Exit")
        
        choice = input("\nEnter choice [1-9]: ").strip()
        seq += 1

        if choice == "1":
            publish_packet("Normal Resting", seq=seq, heart_rate=68, spo2=99, is_moving=False, last_movement_min=2.1)
        elif choice == "2":
            publish_packet("Active Walking", seq=seq, heart_rate=95, spo2=98, is_moving=True, last_movement_min=0.0, accel_mag=1.25)
        elif choice == "3":
            publish_packet("FALL EMERGENCY", seq=seq, heart_rate=105, spo2=97, fall_detected=True, is_emergency=True, risk_level=3, accel_mag=3.1)
        elif choice == "4":
            publish_packet("HYPOXIA EMERGENCY", seq=seq, heart_rate=98, spo2=88, is_emergency=True, risk_level=3)
        elif choice == "5":
            publish_packet("HEATWAVE EMERGENCY", seq=seq, temp_c=42.6, humidity=78.0, heart_rate=123, is_emergency=True, risk_level=3)
        elif choice == "6":
            publish_packet("FLOOD INUNDATION ALERT", seq=seq, temp_c=25.0, humidity=94.0, pressure=1002.5, heart_rate=92, risk_level=2)
        elif choice == "7":
            publish_packet("POLLUTION SMOG ALERT", seq=seq, temp_c=19.5, humidity=88.0, pressure=1021.5, heart_rate=86, risk_level=2)
        elif choice == "8":
            print("\nStreaming real-time telemetry every 5s. Press Ctrl+C to stop.\n")
            try:
                while True:
                    seq += 1
                    publish_packet("Stream", seq=seq)
                    time.sleep(5)
            except KeyboardInterrupt:
                print("\nStream stopped.")
        elif choice == "9":
            break



if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--stream":
        seq = 0
        while True:
            seq += 1
            publish_packet("Stream", seq=seq)
            time.sleep(5)
    else:
        run_interactive()
