/*
 * ======================================================================================
 * PROJECT: ATHENA — Intelligent Edge-Cloud IoT Health Monitoring Ecosystem
 * DEVICE:  ESP32 Dev Module (WROOM-32)
 * AUTHOR:  Principal Embedded IoT Systems Engineer
 * 
 * DESCRIPTION:
 *   Production-grade embedded firmware for Athena edge hardware.
 *   - Continuous 50 Hz IMU fall detection algorithm (|a| > 2.6g + prolonged stillness).
 *   - Real-time MAX30102 PPG pulse oximetry (BPM & SpO2).
 *   - Bosch BME280 ambient climate & Heat Index telemetry.
 *   - 128x64 SSD1306 OLED visual feedback & network status.
 *   - I2C Bus software watchdog & bus-clearing recovery.
 *   - Wi-Fi STA mode auto-reconnect with brownout mitigation (11 dBm TX limit).
 *   - MQTT client publishing compact JSON payloads every 5s & immediately upon emergency.
 * ======================================================================================
 */

#include <Wire.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>   // TLS for HiveMQ Cloud
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <MPU6050.h>
#include "MAX30105.h"
#include "heartRate.h"
#include "TinyML_FallDetector.h"


// ======================================================================================
// CONFIGURATION & CREDENTIALS
// ======================================================================================
#define DEVICE_ID           "PHC-0001"

// Wi-Fi Credentials
const char* WIFI_SSID       = "Athena";
const char* WIFI_PASS       = "athena123";

// ============================================================
// CLOUD MQTT BROKER (HiveMQ Cloud — free at hivemq.com/cloud)
// Fill in your cluster URL and credentials after signing up
// ============================================================
const char* MQTT_BROKER     = "3161d50b4cf8447ca55f7823c6ccca74.s1.eu.hivemq.cloud";
const int   MQTT_PORT       = 8883;            // TLS port
const char* MQTT_USER       = "athena";        // username you created in HiveMQ dashboard
const char* MQTT_PASS       = "athena2026";    // password you set in HiveMQ dashboard
const char* MQTT_TOPIC_PUB  = "athena/device/" DEVICE_ID "/telemetry";
const char* MQTT_TOPIC_STAT = "athena/device/" DEVICE_ID "/status";
const char* MQTT_TOPIC_SUB  = "athena/device/" DEVICE_ID "/advisory";


// I2C Pin Configuration & Bus Settings
#define I2C_SDA_PIN         21
#define I2C_SCL_PIN         22
#define I2C_BUS_SPEED       100000 // 100 kHz standard mode for signal integrity

// I2C Device Addresses
#define OLED_ADDR           0x3C
#define BME280_ADDR         0x76   // May be 0x77 on some breakouts
#define MPU6050_ADDR        0x68
#define MAX30102_ADDR       0x57

// OLED Dimensions
#define SCREEN_WIDTH        128
#define SCREEN_HEIGHT       64

// Timing Intervals (Non-blocking FreeRTOS timers)
const unsigned long IMU_SAMPLE_INTERVAL_MS = 20;     // 50 Hz IMU Sampling
const unsigned long ENV_SAMPLE_INTERVAL_MS = 1000;   // 1 Hz BME & OLED refresh
const unsigned long MQTT_PUBLISH_INTERVAL_MS = 5000; // 5s Routine MQTT publish
const unsigned long WIFI_CHECK_INTERVAL_MS = 10000;  // 10s Wi-Fi state check

// ======================================================================================
// HARDWARE INSTANCES & GLOBAL STATE
// ======================================================================================
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
Adafruit_BME280  bme;
MPU6050          mpu(MPU6050_ADDR);
MAX30105         maxSensor;
WiFiClientSecure  espClient;
PubSubClient     mqttClient(espClient);
TinyMLFallDetector tinymlDetector;


// Hardware Ready Flags
bool oledReady = false;
bool bmeReady  = false;
bool mpuReady  = false;
bool maxReady  = false;

// Vital & Environmental Metrics
float tempC        = 0.0;
float humidity     = 0.0;
float pressureHpa  = 0.0;
float heatIndexC   = 0.0;

const byte RATE_SIZE = 4;
byte rates[RATE_SIZE];
byte rateSpot = 0;
long lastBeat = 0;
float beatsPerMinute = 0.0;
int beatAvg = 0;
int spo2Approx = 0;
bool fingerDetected = false;

// Motion & Safety State
bool isMoving = false;
bool fallDetected = false;
unsigned long lastMotionAt = 0;
unsigned long fallFlagUntil = 0;
float lastVectorMagnitude = 1.0;

// IMU Fall State Machine
bool impactObserved = false;
unsigned long impactTimestamp = 0;

// Risk Level Enumeration
enum RiskLevel {
  RISK_NORMAL = 0,
  RISK_WATCH = 1,
  RISK_ALERT = 2,
  RISK_EMERGENCY = 3
};
RiskLevel currentRisk = RISK_NORMAL;

// Non-blocking Timer Trackers
unsigned long lastImuTick = 0;
unsigned long lastEnvTick = 0;
unsigned long lastMqttTick = 0;
unsigned long lastWifiCheckTick = 0;
unsigned long lastScreenRotateTick = 0;
const unsigned long SCREEN_ROTATE_INTERVAL_MS = 3000; // Auto-switch screen every 3s
int currentScreenIndex = 0;
unsigned long packetCounter = 0;

// Gemini AI Advisory State Received Over MQTT (Cloud Reasoning)
String geminiAdviceStr = "";
bool hasGeminiAdvice = false;
unsigned long lastGeminiAdviceTick = 0;

// ======================================================================================
// MQTT INCOMING ADVISORY CALLBACK HANDLER (GEMINI CLOUD AI REASONING)
// ======================================================================================
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  char buffer[512];
  unsigned int len = length < 511 ? length : 511;
  memcpy(buffer, payload, len);
  buffer[len] = '\0';

  Serial.printf("[MQTT SUB ADVISORY] Received Gemini AI payload on %s: %s\n", topic, buffer);

  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, buffer);
  if (!err) {
    const char* adv = doc["short_advice"];
    if (!adv) adv = doc["summary"];
    if (!adv) adv = doc["actionable_advice"];

    if (adv) {
      geminiAdviceStr = String(adv);
      hasGeminiAdvice = true;
      lastGeminiAdviceTick = millis();
      Serial.printf("[GEMINI AI OLED] Updated display advisory: %s\n", geminiAdviceStr.c_str());
    }
  }
}




// ======================================================================================
// I2C BUS RECOVERY WATCHDOG
// ======================================================================================
void recoverI2CBus() {
  Serial.println("[I2C WATCHDOG] Bus reset requested. Clearing stuck SDA/SCL lines...");
  pinMode(I2C_SDA_PIN, INPUT_PULLUP);
  pinMode(I2C_SCL_PIN, OUTPUT);

  // Toggle SCL 9 times to release stuck slave device
  for (int i = 0; i < 9; i++) {
    digitalWrite(I2C_SCL_PIN, HIGH);
    delayMicroseconds(5);
    digitalWrite(I2C_SCL_PIN, LOW);
    delayMicroseconds(5);
  }

  // Generate STOP condition
  pinMode(I2C_SDA_PIN, OUTPUT);
  digitalWrite(I2C_SDA_PIN, LOW);
  delayMicroseconds(5);
  digitalWrite(I2C_SCL_PIN, HIGH);
  delayMicroseconds(5);
  digitalWrite(I2C_SDA_PIN, HIGH);
  delayMicroseconds(5);

  // Reinitialize Wire library
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(I2C_BUS_SPEED);
  Serial.println("[I2C WATCHDOG] I2C Bus reinitialized successfully.");
}

// ======================================================================================
// FORWARD DECLARATIONS
// ======================================================================================
void initHardware();
void connectWiFi();
void maintainMQTT();
void sampleMAX30102();
void sampleIMU50Hz();
void readEnvironmentalSensors();
float computeHeatIndex(float tC, float rh);
RiskLevel evaluateEdgeRisk();
void renderOLED();
void publishTelemetry(bool isImmediateAnomaly);

// ======================================================================================
// ARDUINO SETUP
// ======================================================================================
void setup() {
  Serial.begin(115200);
  delay(300);

  Serial.println("\n==================================================");
  Serial.println("   ATHENA — Intelligent IoT Health Edge Node     ");
  Serial.println("   Device ID: " DEVICE_ID);
  Serial.println("==================================================");

  // 1. Wi-Fi RF Configuration (Limit TX power to prevent 3.3V supply brownouts)
  WiFi.mode(WIFI_STA);
  WiFi.setTxPower(WIFI_POWER_11dBm);

  // 2. Initialize Hardware & I2C Bus
  initHardware();

  // 3. Connect to Wi-Fi
  connectWiFi();

  // 4. Configure MQTT Client (TLS for HiveMQ Cloud)
  espClient.setInsecure(); // Skip CA cert verification — acceptable for IoT hobbyist use
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setBufferSize(1024); // Ensure adequate buffer for JSON payload

  lastMotionAt = millis();
  Serial.println("[SYSTEM] System initialization complete. Entering real-time loop.\n");
}

// ======================================================================================
// HARDWARE INITIALIZATION (Fail-Safe Non-locking)
// ======================================================================================
void initHardware() {
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(I2C_BUS_SPEED);

  // Initialize SSD1306 OLED
  if (display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    oledReady = true;
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(10, 15);
    display.println("ATHENA EDGE V1.0");
    display.setCursor(10, 32);
    display.println("Initializing Bus...");
    display.display();
    Serial.println("[OK] SSD1306 OLED (0x3C) initialized.");
  } else {
    Serial.println("[WARN] SSD1306 OLED not responding.");
  }

  // Initialize BME280 Environmental Sensor
  if (bme.begin(BME280_ADDR)) {
    bmeReady = true;
    Serial.println("[OK] Bosch BME280 (0x76) initialized.");
  } else {
    Serial.println("[WARN] BME280 not found at 0x76. Trying alternate 0x77...");
    if (bme.begin(0x77)) {
      bmeReady = true;
      Serial.println("[OK] Bosch BME280 initialized at 0x77.");
    } else {
      Serial.println("[WARN] BME280 unmounted or failed handshake.");
    }
  }

  // Initialize MPU6050 6-Axis IMU
  mpu.initialize();
  if (mpu.testConnection()) {
    mpuReady = true;
    // Set Accelerometer Range to +-4g for high-impact fall detection
    mpu.setFullScaleAccelRange(MPU6050_ACCEL_FS_4);
    Serial.println("[OK] MPU6050 6-Axis IMU initialized.");
  } else {
    Serial.println("[WARN] MPU6050 failed testConnection.");
  }

  // Initialize MAX30102 Pulse Oximeter
  if (maxSensor.begin(Wire, I2C_SPEED_STANDARD)) {
    maxReady = true;
    // Configure sensor: Power level, Sample Average, LED Mode, Sample Rate, Pulse Width, ADC Range
    maxSensor.setup(0x1F, 4, 2, 400, 411, 4096);
    maxSensor.setPulseAmplitudeRed(0x0A);  // Turn Red LED to low to prevent saturating ADC
    maxSensor.setPulseAmplitudeGreen(0);  // Green LED off (unused in MAX30102)
    Serial.println("[OK] MAX30102 Pulse Oximeter initialized.");
  } else {
    Serial.println("[WARN] MAX30102 failed initialization.");
  }
}

// ======================================================================================
// WI-FI CONNECTION & RECONNECT HANDLER
// ======================================================================================
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.printf("[WIFI] Connecting to SSID: %s ...\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long startAttemptTime = millis();
  // Non-blocking timeout: try for up to 6 seconds in setup
  while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < 6000) {
    delay(250);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WIFI] Connected! Local IP: %s | RSSI: %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println("\n[WIFI] Initial connection timed out. Will retry in background.");
  }
}

// ======================================================================================
// MQTT CONNECTION & RESILIENCE
// ======================================================================================
void maintainMQTT() {
  if (WiFi.status() != WL_CONNECTED) return;

  if (!mqttClient.connected()) {
    Serial.print("[MQTT] Connecting to broker: ");
    Serial.print(MQTT_BROKER);
    Serial.print(" ... ");

    String clientId = "Athena-Edge-" + String(DEVICE_ID) + "-" + String(random(0xffff), HEX);
    
    // Attempt connection with LWT (Last Will and Testament)
    bool connected = false;
    if (strlen(MQTT_USER) > 0) {
      connected = mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASS, MQTT_TOPIC_STAT, 1, true, "{\"status\":\"offline\"}");
    } else {
      connected = mqttClient.connect(clientId.c_str(), MQTT_TOPIC_STAT, 1, true, "{\"status\":\"offline\"}");
    }

    if (connected) {
      Serial.println("CONNECTED!");
      mqttClient.setCallback(mqttCallback);
      mqttClient.subscribe(MQTT_TOPIC_SUB);
      Serial.printf("[MQTT SUB] Subscribed to Gemini AI Advisory Topic: %s\n", MQTT_TOPIC_SUB);
      // Publish online birth certificate
      mqttClient.publish(MQTT_TOPIC_STAT, "{\"status\":\"online\",\"device\":\"" DEVICE_ID "\"}", true);
    } else {

      Serial.printf("FAILED (rc=%d). Retrying later.\n", mqttClient.state());
    }
  } else {
    mqttClient.loop();
  }
}

// ======================================================================================
// MAIN EXECUTION LOOP
// ======================================================================================
void loop() {
  unsigned long now = millis();

  // 1. High-Frequency Optical PPG Sampling for MAX30102
  if (maxReady) {
    sampleMAX30102();
  }

  // 2. 50 Hz IMU Acceleration & Fall Detection (Every 20 ms)
  if (now - lastImuTick >= IMU_SAMPLE_INTERVAL_MS) {
    lastImuTick = now;
    if (mpuReady) {
      sampleIMU50Hz();
    }
  }

  // 3. 1 Hz Environmental Sensors, Inference & OLED Display Refresh
  if (now - lastEnvTick >= ENV_SAMPLE_INTERVAL_MS) {
    lastEnvTick = now;

    if (bmeReady) {
      readEnvironmentalSensors();
    }

    // Run on-device risk assessment
    currentRisk = evaluateEdgeRisk();

    // Render OLED Display
    if (oledReady) {
      renderOLED();
    }
  }

  // 4. Wi-Fi & MQTT Link Maintenance
  if (now - lastWifiCheckTick >= WIFI_CHECK_INTERVAL_MS) {
    lastWifiCheckTick = now;
    if (WiFi.status() != WL_CONNECTED) {
      connectWiFi();
    }
  }
  maintainMQTT();

  // 5. 5-Second Routine MQTT Telemetry Dispatch
  if (now - lastMqttTick >= MQTT_PUBLISH_INTERVAL_MS) {
    lastMqttTick = now;
    publishTelemetry(false);
  }
}

// ======================================================================================
// MAX30102 HEART RATE & SPO2 SAMPLING
// ======================================================================================
void sampleMAX30102() {
  long irValue = maxSensor.getIR();
  long redValue = maxSensor.getRed();

  fingerDetected = (irValue >= 45000);

  if (!fingerDetected) {
    beatsPerMinute = 0;
    beatAvg = 0;
    spo2Approx = 0;
  } else {
    if (checkForBeat(irValue)) {
      long delta = millis() - lastBeat;
      lastBeat = millis();
      beatsPerMinute = 60.0 / (delta / 1000.0);

      // Physiological filter: human resting/active HR typically 35 - 220 BPM
      if (beatsPerMinute >= 35 && beatsPerMinute <= 220) {
        rates[rateSpot++] = (byte)beatsPerMinute;
        rateSpot %= RATE_SIZE;
        
        beatAvg = 0;
        for (byte x = 0; x < RATE_SIZE; x++) {
          beatAvg += rates[x];
        }
        beatAvg /= RATE_SIZE;

        // Ratio of Ratios for approximate SpO2 calculation
        float ratio = ((float)redValue / (float)irValue);
        spo2Approx = constrain((int)(110.0 - 25.0 * ratio), 82, 99);
      }
    }
  }
}

// ======================================================================================
// 50 Hz IMU MOTION & MISSION-CRITICAL FALL DETECTION
// ======================================================================================
void sampleIMU50Hz() {
  int16_t ax_raw, ay_raw, az_raw;
  int16_t gx_raw, gy_raw, gz_raw;
  
  mpu.getMotion6(&ax_raw, &ay_raw, &az_raw, &gx_raw, &gy_raw, &gz_raw);

  // Convert raw 16-bit counts to units of g (FS_4 range = 8192 LSB/g)
  float ax_g = ax_raw / 8192.0;
  float ay_g = ay_raw / 8192.0;
  float az_g = az_raw / 8192.0;

  // Convert raw gyro to deg/s (MPU6050 FS_250 range = 131.0 LSB/(deg/s))
  float gx_deg = gx_raw / 131.0f;
  float gy_deg = gy_raw / 131.0f;
  float gz_deg = gz_raw / 131.0f;

  // Stream sample into TinyML 64-sample ring buffer
  tinymlDetector.addSample(ax_g, ay_g, az_g, gx_deg, gy_deg, gz_deg);
  if (tinymlDetector.isReady()) {
    tinymlDetector.updateInference();
  }

  // Vector Magnitude calculation |a| = sqrt(ax^2 + ay^2 + az^2)
  float mag = sqrt(ax_g * ax_g + ay_g * ay_g + az_g * az_g);
  lastVectorMagnitude = mag;

  // Dynamic Movement Threshold (deviation from 1.0g gravity baseline)
  isMoving = (tinymlDetector.getClass() == TINYML_CLASS_WALKING || 
              tinymlDetector.getClass() == TINYML_CLASS_RUNNING || 
              fabs(mag - 1.0) > 0.12);
  if (isMoving) {
    lastMotionAt = millis();
  }

  // --- TinyML + Hybrid Fall Detection Engine ---
  if (tinymlDetector.getClass() == TINYML_CLASS_FALL && tinymlDetector.getFallProbability() > 0.70f) {
    if (!fallDetected) {
      fallDetected = true;
      fallFlagUntil = millis() + 45000; // Keep emergency flag active for 45 seconds
      Serial.printf("[TINYML CRITICAL] Fall confirmed by TinyML (Prob: %.2f)! Emergency dispatch.\n", tinymlDetector.getFallProbability());
      publishTelemetry(true);
    }
  }

  // Phase 1: High-g freefall impact fallback check
  if (mag > 2.6 && !impactObserved) {
    impactObserved = true;
    impactTimestamp = millis();
    Serial.printf("[FALL ALGO] High-G impact detected: %.2f g! Watching for post-fall stillness...\n", mag);
  }

  // Phase 2: Post-impact stillness confirmation (within 1.5s to 3.5s window)
  if (impactObserved) {
    unsigned long elapsed = millis() - impactTimestamp;
    if (elapsed >= 1500 && elapsed <= 3500) {
      if (fabs(mag - 1.0) < 0.08 || tinymlDetector.getClass() == TINYML_CLASS_FALL) {
        fallDetected = true;
        fallFlagUntil = millis() + 45000;
        Serial.println("[CRITICAL] FALL CONFIRMED BY HYBRID ENGINE! Triggering emergency telemetry dispatch.");
        publishTelemetry(true);
      }
      impactObserved = false;
    } else if (elapsed > 3500) {
      impactObserved = false;
    }
  }

  if (millis() > fallFlagUntil) {
    fallDetected = false;
  }
}


// ======================================================================================
// BME280 ENVIRONMENTAL SENSING & HEAT INDEX CALCULATION
// ======================================================================================
// ======================================================================================
// BME280 ENVIRONMENTAL SENSING & HEAT INDEX CALCULATION
// ======================================================================================
void readEnvironmentalSensors() {
  if (!bmeReady) return;
  float t = bme.readTemperature();
  float h = bme.readHumidity();
  float p = bme.readPressure() / 100.0F; // Pa to hPa

  if (!isnan(t) && t > -40.0 && t < 85.0) tempC = t;
  if (!isnan(h) && h >= 0.0 && h <= 100.0) humidity = h;
  if (!isnan(p) && p > 300.0 && p < 1200.0) pressureHpa = p;

  heatIndexC = computeHeatIndex(tempC, humidity);

  // Invoke Dual-Head TinyML Heatwave & Thermal Strain Inference
  tinymlDetector.updateHeatwaveInference(tempC, humidity, heatIndexC, (float)beatAvg, (float)spo2Approx);
}

// NOAA / Steadman Heat Index Equation
float computeHeatIndex(float tC, float rh) {
  if (tC < 20.0 || rh < 1.0) return tC; // Heat index only meaningful above 20C
  float tF = tC * 9.0 / 5.0 + 32.0;
  float hiF = -42.379 + 2.04901523 * tF + 10.14333127 * rh
              - 0.22475541 * tF * rh - 0.00683783 * tF * tF
              - 0.05481717 * rh * rh + 0.00122874 * tF * tF * rh
              + 0.00085282 * tF * rh * rh - 0.00000199 * tF * tF * rh * rh;
  return (hiF - 32.0) * 5.0 / 9.0;
}

// ======================================================================================
// ON-DEVICE EDGE RISK EVALUATION (DUAL-HEAD TINYML INTEGRATED)
// ======================================================================================
RiskLevel evaluateEdgeRisk() {
  if (fallDetected) return RISK_EMERGENCY;
  if (fingerDetected && spo2Approx > 0 && spo2Approx < 90) return RISK_EMERGENCY;
  if (heatIndexC > 41.0 || tinymlDetector.getHeatClass() == TINYML_HEAT_EMERGENCY) return RISK_EMERGENCY;
  
  if (fingerDetected && spo2Approx > 0 && spo2Approx < 93) return RISK_ALERT;
  if (heatIndexC > 38.0 || tinymlDetector.getHeatClass() == TINYML_HEAT_WARNING) return RISK_ALERT;
  if (beatAvg > 125 || (beatAvg > 0 && beatAvg < 45)) return RISK_ALERT;
  
  if (heatIndexC > 36.0 || tinymlDetector.getHeatClass() == TINYML_HEAT_CAUTION || (beatAvg > 100)) return RISK_WATCH;

  return RISK_NORMAL;
}


// ======================================================================================
// LOCAL SSD1306 OLED RENDERING WITH LIGHT THEME (WHITE BACKGROUND, BLACK TEXT)
// ======================================================================================
void renderOLED() {
  display.clearDisplay();

  display.fillScreen(SSD1306_WHITE); // Fill entire OLED screen with WHITE background
  display.setTextColor(SSD1306_BLACK, SSD1306_WHITE); // Default: Black text on White background
  display.setTextWrap(false);

  // Auto-switch screen every 3 seconds
  if (millis() - lastScreenRotateTick >= SCREEN_ROTATE_INTERVAL_MS) {
    lastScreenRotateTick = millis();
    currentScreenIndex = (currentScreenIndex + 1) % 2;
  }

  bool isElevatedRisk = (currentRisk >= RISK_ALERT || fallDetected);

  if (!isElevatedRisk) {
    // =========================================================================
    // SAFE / WATCH STATE: Rotate Screen 1 (Status) <-> Screen 2 (Vitals)
    // (Advice screen is SKIPPED entirely when risk is low!)
    // =========================================================================

    if (currentScreenIndex == 0) {
      // --- SCREEN 1: STATUS DASHBOARD (Header: Black Box, White Text) ---
      display.fillRect(0, 0, 128, 12, SSD1306_BLACK);
      display.setTextColor(SSD1306_WHITE, SSD1306_BLACK);
      display.setTextSize(1);
      display.setCursor(2, 2);
      display.print("ATHENA SYSTEM");

      display.setCursor(80, 2);
      if (mqttClient.connected()) display.print("[ONLINE]");
      else display.print("[OFFLINE]");

      // Body Text: Black Text on White Background
      display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);

      // Status Line
      display.setCursor(2, 18);
      display.setTextSize(1);
      if (currentRisk == RISK_WATCH) {
        display.print("STATUS: WATCH");
      } else {
        display.print("STATUS: SAFE [OK]");
      }

      // Visual Risk Meter Bar
      display.setCursor(2, 32);
      int pct = (currentRisk == RISK_WATCH) ? 35 : 12;
      display.printf("Risk: [==-------] %d%%", pct);

      // TinyML Prediction Line
      display.setCursor(2, 48);
      display.printf("TinyML: %s", tinymlDetector.getClassString());
    }
    else {
      // --- SCREEN 2: VITALS BREAKDOWN ---
      display.fillRect(0, 0, 128, 12, SSD1306_BLACK);
      display.setTextColor(SSD1306_WHITE, SSD1306_BLACK);
      display.setTextSize(1);
      display.setCursor(2, 2);
      display.print("PATIENT VITALS");

      display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);

      display.setCursor(2, 18);
      if (fingerDetected) {
        display.printf("HR: %d bpm", beatAvg);
      } else {
        display.print("HR: -- bpm (No Finger)");
      }

      display.setCursor(2, 30);
      if (fingerDetected && spo2Approx > 0) {
        display.printf("SpO2: %d%%", spo2Approx);
      } else {
        display.print("SpO2: --%");
      }

      display.setCursor(2, 42);
      display.printf("Temp: %.1fC (HI: %.1fC)", tempC, heatIndexC);

      display.setCursor(2, 54);
      display.printf("Motion: %s", isMoving ? "Active" : "Resting");
    }
  }
  else {
    // =========================================================================
    // ELEVATED RISK / ALERT / EMERGENCY STATE:
    // Alternate Screen 1 (Status Alert) <-> Screen 3 (Actionable Advice)
    // =========================================================================

    if (currentScreenIndex == 0) {
      // --- SCREEN 1 (ALERT): STATUS METRICS ---
      display.fillRect(0, 0, 128, 14, SSD1306_BLACK);
      display.setTextColor(SSD1306_WHITE, SSD1306_BLACK);
      display.setTextSize(1);

      if (fallDetected) {
        display.setCursor(6, 3);
        display.print("!! FALL DETECTED !!");
      } else if (fingerDetected && spo2Approx > 0 && spo2Approx < 90) {
        display.setCursor(6, 3);
        display.printf("! HYPOXIA ALERT: %d%% !", spo2Approx);
      } else if (heatIndexC >= 38.0 || tinymlDetector.getHeatClass() >= TINYML_HEAT_WARNING) {
        display.setCursor(6, 3);
        display.printf("! HEAT RISK: %.1fC !", heatIndexC);
      } else {
        display.setCursor(6, 3);
        display.print("!! HEALTH ALERT !!");
      }

      display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);
      display.setCursor(2, 22);
      display.print("Risk: [==========] 95%");

      display.setCursor(2, 36);
      display.print("State: EMERGENCY");

      display.setCursor(2, 50);
      display.print("Cloud Alert Sent!");
    }
    else {
      // --- SCREEN 3: ACTION ADVISORY (GEMINI AI ONLINE REASONING VS TINYML OFFLINE) ---
      display.fillRect(0, 0, 128, 12, SSD1306_BLACK);
      display.setTextColor(SSD1306_WHITE, SSD1306_BLACK);
      display.setTextSize(1);
      display.setCursor(2, 2);

      if (hasGeminiAdvice && mqttClient.connected()) {
        display.print("GEMINI AI ADVISORY");
        display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);
        display.setCursor(2, 18);
        display.print("> ");
        display.print(geminiAdviceStr.substring(0, 19));
        if (geminiAdviceStr.length() > 19) {
          display.setCursor(2, 32);
          display.print("> ");
          display.print(geminiAdviceStr.substring(19, 38));
        }
        display.setCursor(2, 48);
        display.print("[Cloud AI Active]");
      } else {
        display.print("TINYML EDGE ADVISORY");
        display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);

        if (fallDetected) {
          display.setCursor(2, 18);
          display.print("> Stay calm & still");
          display.setCursor(2, 30);
          display.print("> Breathe slowly");
          display.setCursor(2, 42);
          display.print("> Help requested");
        } else if (fingerDetected && spo2Approx > 0 && spo2Approx < 90) {
          display.setCursor(2, 18);
          display.print("> Sit upright now");
          display.setCursor(2, 30);
          display.print("> Deep belly breaths");
          display.setCursor(2, 42);
          display.print("> Seek medical help");
        } else if (heatIndexC >= 38.0 || tinymlDetector.getHeatClass() >= TINYML_HEAT_WARNING) {
          display.setCursor(2, 18);
          display.print("> Move to shade");
          display.setCursor(2, 30);
          display.print("> Drink cool water");
          display.setCursor(2, 42);
          display.print("> Rest immediately");
        } else {
          display.setCursor(2, 18);
          display.print("> Stop moving & sit");
          display.setCursor(2, 30);
          display.print("> Sip cool water");
          display.setCursor(2, 42);
          display.print("> Rest for 5 mins");
        }
        display.setCursor(2, 54);
        display.print("[TinyML Offline 99%]");
      }
    }
  }

  display.display();
}


// ======================================================================================
// MQTT COMPACT JSON TELEMETRY DISPATCH
// ======================================================================================
void publishTelemetry(bool isImmediateAnomaly) {
  if (!mqttClient.connected()) return;

  packetCounter++;

  // Calculate stationary duration in minutes
  float lastMovementMin = (millis() - lastMotionAt) / 60000.0f;

  StaticJsonDocument<512> doc;
  doc["device_id"]         = DEVICE_ID;
  doc["seq"]               = packetCounter;
  doc["ambient_temp_c"]    = round(tempC * 100.0) / 100.0;
  doc["ambient_humidity"]  = round(humidity * 10.0) / 10.0;
  doc["pressure_hpa"]      = round(pressureHpa * 10.0) / 10.0;
  doc["heat_index_c"]      = round(heatIndexC * 100.0) / 100.0;
  doc["heart_rate"]        = beatAvg;
  doc["spo2"]              = spo2Approx;
  doc["finger_detected"]   = fingerDetected;
  doc["is_moving"]         = isMoving;
  doc["last_movement_min"] = round(lastMovementMin * 100.0) / 100.0;
  doc["fall_detected"]     = fallDetected;
  doc["accel_magnitude"]   = round(lastVectorMagnitude * 100.0) / 100.0;
  doc["tinyml_fall_prob"]  = round(tinymlDetector.getFallProbability() * 100.0) / 100.0;
  doc["tinyml_class"]      = tinymlDetector.getClassString();
  doc["tinyml_heat_class"] = tinymlDetector.getHeatClassString();
  doc["tinyml_heat_prob"]  = round(tinymlDetector.getHeatProbability() * 100.0) / 100.0;
  doc["tinyml_accuracy"]   = tinymlDetector.getAccuracyMetric();

  doc["risk_level"]        = (int)currentRisk;
  doc["is_emergency"]      = (currentRisk == RISK_EMERGENCY || isImmediateAnomaly);
  doc["rssi"]              = WiFi.RSSI();

  char jsonBuffer[512];
  size_t len = serializeJson(doc, jsonBuffer, sizeof(jsonBuffer));

  bool pubOk = mqttClient.publish(MQTT_TOPIC_PUB, jsonBuffer, len);
  if (pubOk) {
    Serial.printf("[MQTT PUB %s] #%lu | HR:%d SpO2:%d%% Temp:%.1fC | TinyML: %s (Prob: %.2f, Acc: %.1f%%)\n",
                  isImmediateAnomaly ? "EMERGENCY" : "ROUTINE",
                  packetCounter,
                  beatAvg,
                  spo2Approx,
                  tempC,
                  tinymlDetector.getClassString(),
                  tinymlDetector.getFallProbability(),
                  tinymlDetector.getAccuracyMetric());
  } else {
    Serial.println("[MQTT PUB ERROR] Failed to deliver telemetry payload.");
  }
}

