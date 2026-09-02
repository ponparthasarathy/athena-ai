# Athena IoT Health Ecosystem — Complete Deployment Guide

This guide provides end-to-end instructions for deploying the **Athena** IoT health monitoring ecosystem across hardware, cloud backend, MQTT brokers, and web dashboards.

---

## 1. Quickstart (Run Locally in 2 Minutes)

### Step 1: Install Python Dependencies
Ensure Python 3.10+ is installed on your machine.
```bash
cd e:/Athena/backend
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Open `e:/Athena/backend/.env` and verify your Gemini API key and MQTT Broker settings:
```env
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
GEMINI_MODEL=gemini-2.5-flash
MQTT_BROKER_HOST=broker.hivemq.com
MQTT_BROKER_PORT=1883
PORT=8000
HOST=0.0.0.0
```

### Step 3: Start the Backend Server
```bash
python server.py
```
Your server will start and serve both the REST API and the live Web Dashboard at:
👉 **`http://localhost:8000/`**

### Step 4: Test with Telemetry Simulator (Optional)
In a second terminal window, run:
```bash
python simulator.py
```
Select scenarios (1 to 6) to emit live telemetry packets and watch Gemini AI evaluate the health state on your browser dashboard in real time!

---

## 2. MQTT Broker Configuration Guide

Athena uses MQTT for ultralight, bi-directional telemetry. You can choose any of the following broker options:

### Option A: Public Free Broker (Fastest for testing)
* Host: `broker.hivemq.com` or `broker.emqx.io`
* Port: `1883` (TCP)
* Username/Password: *None*
* *Already configured as default in firmware and backend.*

### Option B: Free HiveMQ Cloud Cluster (Recommended for Secure Production)
1. Sign up for free at [HiveMQ Cloud](https://www.hivemq.com/cloud/).
2. Create a Free Serverless Cluster.
3. Note your Cluster URL (e.g., `xxxxxx.s1.eu.hivemq.cloud`) and Port (`8883` for TLS).
4. Create an MQTT user credentials (username and password) in the Access Management tab.
5. In `backend/.env` and `Athena_firmware.ino`, update:
   - `MQTT_BROKER_HOST=xxxxxx.s1.eu.hivemq.cloud`
   - `MQTT_BROKER_PORT=8883`
   - `MQTT_USERNAME=your_username`
   - `MQTT_PASSWORD=your_password`

### Option C: Local Mosquitto via Docker Compose
Run the bundled `docker-compose.yml`:
```bash
docker-compose up -d
```
This boots up Mosquitto on port `1883` alongside the Athena server.

---

## 3. ESP32 Edge Firmware Flashing Guide

### Required Arduino IDE Libraries
Open **Arduino IDE** -> **Tools** -> **Manage Libraries...** and install the following:

1. **PubSubClient** (by Nick O'Leary)
2. **ArduinoJson** (by Benoit Blanchon, v6 or v7)
3. **Adafruit SSD1306** (by Adafruit)
4. **Adafruit GFX Library** (by Adafruit)
5. **Adafruit BME280 Library** (by Adafruit)
6. **Adafruit Unified Sensor** (by Adafruit)
7. **MPU6050** (by Electronic Cats or Jeff Rowberg)
8. **SparkFun MAX3010x Pulse and Proximity Sensor Library** (by SparkFun)

### Arduino IDE Board Settings:
* **Board**: "ESP32 Dev Module" (or "DOIT ESP32 DEVKIT V1")
* **Flash Frequency**: `80MHz`
* **Upload Speed**: `921600` or `115200`
* **Partition Scheme**: `Default 4MB with spiffs (1.2MB APP / 1.5MB SPIFFS)`
* **Port**: Select your ESP32 COM port (e.g., `COM3`, `COM4` on Windows)

### Flashing Steps:
1. Open `e:/Athena/firmware/Athena_firmware/Athena_firmware.ino` in Arduino IDE.
2. Update your Wi-Fi credentials:
   ```cpp
   const char* WIFI_SSID = "YOUR_WIFI_NAME";
   const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
   ```
3. If using custom MQTT broker:
   ```cpp
   const char* MQTT_BROKER = "broker.hivemq.com";
   const int   MQTT_PORT   = 1883;
   ```
4. Click **Upload** (hold the `BOOT` button on ESP32 if the flash process is waiting for connection).
5. Open Serial Monitor at **115200 baud** to view real-time initialization and MQTT transmission logs.

---

## 4. Cloud Deployment (Render / Railway / Docker)

### Deploying to Render.com (Free Web Service)
1. Push this repository to GitHub or GitLab.
2. Go to [Render Dashboard](https://dashboard.render.com/) -> **New** -> **Web Service**.
3. Connect your repository.
4. Select **Docker** environment (or Python):
   - Build Command (Python): `pip install -r backend/requirements.txt`
   - Start Command: `uvicorn backend.server:app --host 0.0.0.0 --port $PORT`
5. Add Environment Variables:
   - `GEMINI_API_KEY` = `YOUR_GEMINI_API_KEY_HERE`
   - `GEMINI_MODEL` = `gemini-2.5-flash`
   - `MQTT_BROKER_HOST` = `broker.hivemq.com`
   - `MQTT_BROKER_PORT` = `1883`
6. Click **Create Web Service**. Your dashboard and WebSocket stream will be available globally over HTTPS/WSS!

---

## 5. System Health Check & Verification

Once deployed, you can verify your ecosystem health by accessing:
* **Healthcheck API**: `GET /api/health`
* **Active Devices API**: `GET /api/devices`
* **Trigger Manual Gemini Evaluation**: `POST /api/device/PHC-0001/evaluate`
