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
import paho.mqtt.client as mqtt

MQTT_BROKER = os.getenv("MQTT_BROKER_HOST", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
DEVICE_ID = os.getenv("DEVICE_ID", "PHC-0001")
TOPIC = f"athena/device/{DEVICE_ID}/telemetry"

print("\n==================================================")
print("   ATHENA IOT TELEMETRY SIMULATOR")
print(f"   Target Broker: {MQTT_BROKER}:{MQTT_PORT}")
print(f"   Target Device: {DEVICE_ID}")
print("==================================================")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"Athena-Sim-{random.randint(1000, 9999)}")
try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    print("[OK] Connected to MQTT broker.")
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
        "risk_level": kwargs.get("risk_level", 0),
        "is_emergency": kwargs.get("is_emergency", False),
        "rssi": -60 + random.randint(-5, 5),
        "timestamp": now_iso
    }

    msg = json.dumps(payload)
    client.publish(TOPIC, msg)
    print(f"[{scenario_name.upper()}] Sent payload -> HR: {payload['heart_rate']} bpm | SpO2: {payload['spo2']}% | Temp: {payload['ambient_temp_c']}°C | Fall: {payload['fall_detected']}")


def run_interactive():
    seq = 0
    while True:
        print("\nSelect Scenario to Emit:")
        print("1. Routine Normal Vitals (Resting)")
        print("2. Normal Active / Walking Vitals")
        print("3. EMERGENCY: High-G Fall Detected + Post-Impact Stillness")
        print("4. EMERGENCY: Severe Hypoxia (SpO2 88%)")
        print("5. ALERT: Heat Wave Stress (Temp 39°C, HR 112 BPM)")
        print("6. Continuous Live Stream (Routine every 5 seconds)")
        print("7. Exit")
        
        choice = input("\nEnter choice [1-7]: ").strip()
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
            publish_packet("HEAT STRESS ALERT", seq=seq, temp_c=39.2, humidity=68.0, heart_rate=114, is_emergency=False, risk_level=2)
        elif choice == "6":
            print("\nStreaming real-time telemetry every 5s. Press Ctrl+C to stop.\n")
            try:
                while True:
                    seq += 1
                    publish_packet("Stream", seq=seq)
                    time.sleep(5)
            except KeyboardInterrupt:
                print("\nStream stopped.")
        elif choice == "7":
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
