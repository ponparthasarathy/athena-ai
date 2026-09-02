# Athena IoT Health Monitor — Hardware Wiring Guide & Circuit Map

This document details the exact pin-to-pin wiring connections, power distribution guidelines, I2C address map, and circuit best practices for assembling the **Athena Edge Unit**.

---

## 1. System Architecture & Bus Topology

All sensors and the display communicate with the ESP32 (WROOM-32) via a single shared **I2C Bus** operating at **100 kHz Standard Mode** to ensure bus stability over short wire leads.

- **Primary I2C Data (SDA)**: `GPIO 21`
- **Primary I2C Clock (SCL)**: `GPIO 22`
- **Logic Voltage**: `3.3V DC`

```
                        +-------------------+
                        |   ESP32 DevKit    |
                        |     (WROOM-32)    |
                        +---------+---------+
                                  |
                +-----------------+-----------------+
                | 3.3V (VCC)      | GND             |
                | GPIO 21 (SDA)   | GPIO 22 (SCL)   |
                +--------+--------+--------+--------+
                         |                 |
       +-----------------+-----------------+-----------------+
       |                 |                 |                 |
+------+------+   +------+------+   +------+------+   +------+------+
|   MAX30102  |   |   BME280    |   |   MPU6050   |   |   SSD1306   |
| Pulse Oxim. |   | Env. Sensor |   | 6-Axis IMU  |   |  OLED Disp  |
|  (0x57)     |   |  (0x76)     |   |  (0x68)     |   |  (0x3C)     |
+-------------+   +-------------+   +-------------+   +-------------+
```

---

## 2. Complete Pin-to-Pin Wiring Table

| Component | Sensor Pin | ESP32 Pin | Function / Description | Wire Color (Recommended) |
| :--- | :--- | :--- | :--- | :--- |
| **Power Bus** | Common VCC | **3V3 (or 3.3V)** | Regulated 3.3V Power Supply | 🔴 Red |
| **Power Bus** | Common GND | **GND** | System Ground Reference | ⚫ Black |
| **MAX30102** | VIN / VCC | **3V3** | Power supply (3.3V) | 🔴 Red |
| | GND | **GND** | Ground | ⚫ Black |
| | SDA | **GPIO 21** | I2C Serial Data | 🟢 Green |
| | SCL | **GPIO 22** | I2C Serial Clock | 🟡 Yellow |
| | INT | *NC / Float* | Interrupt (not required in polled mode) | — |
| **BME280** | VCC / VIN | **3V3** | Power supply (3.3V) | 🔴 Red |
| | GND | **GND** | Ground | ⚫ Black |
| | SCL | **GPIO 22** | I2C Serial Clock | 🟡 Yellow |
| | SDA | **GPIO 21** | I2C Serial Data | 🟢 Green |
| | SDO / ADDR | **GND** | Selects I2C address `0x76` (pull high for `0x77`)| ⚫ Black (or onboard jumper) |
| | CS | **3V3** | Selects I2C Mode (High = I2C, Low = SPI) | 🔴 Red |
| **MPU6050** | VCC | **3V3** (or 5V if module has AMS1117 regulator) | Power | 🔴 Red |
| | GND | **GND** | Ground | ⚫ Black |
| | SCL | **GPIO 22** | I2C Serial Clock | 🟡 Yellow |
| | SDA | **GPIO 21** | I2C Serial Data | 🟢 Green |
| | AD0 | **GND** | Selects I2C address `0x68` (High = `0x69`) | ⚫ Black |
| | INT | *NC* | Interrupt (polled at 50Hz in firmware) | — |
| **SSD1306 (128x64)** | VCC | **3V3** | Power supply (3.3V) | 🔴 Red |
| | GND | **GND** | Ground | ⚫ Black |
| | SCL | **GPIO 22** | I2C Serial Clock | 🟡 Yellow |
| | SDA | **GPIO 21** | I2C Serial Data | 🟢 Green |

---

## 3. I2C Address Verification Map

When the ESP32 performs an I2C scan on `Wire.begin(21, 22)`, the following hex addresses will be reported:

| Device | Hex Address | Binary Address | Note |
| :--- | :--- | :--- | :--- |
| **SSD1306 OLED** | `0x3C` | `0b0111100` | Common address for 0.96" 128x64 displays |
| **MAX30102** | `0x57` | `0b1010111` | Fixed factory address by Maxim Integrated |
| **MPU6050** | `0x68` | `0b1101000` | When AD0 pin is tied to GND |
| **BME280** | `0x76` | `0b1110110` | When SDO is GND (Bosch Sensortec default) |

---

## 4. Hardware Assembly & Circuit Stability Tips

1. **Pull-Up Resistors**:
   - Most sensor breakouts (Adafruit, SparkFun, generic GY modules) include onboard $4.7\text{k}\Omega$ or $10\text{k}\Omega$ pull-up resistors on SDA and SCL to 3.3V.
   - If using long hookup jumper wires (> 15 cm), place two external $4.7\text{k}\Omega$ pull-up resistors from GPIO 21 (SDA) to 3.3V, and from GPIO 22 (SCL) to 3.3V.
2. **Brownout Prevention (Wi-Fi Transmit Burst Protection)**:
   - ESP32 Wi-Fi bursts can pull up to 350mA spikes, causing 3.3V voltage drops that can reset the MAX30102 or MPU6050.
   - In firmware, RF power is limited via `WiFi.setTxPower(WIFI_POWER_11dBm)`.
   - On hardware, place a **$100\mu\text{F}$ to $470\mu\text{F}$ Electrolytic Capacitor** across the ESP32 `3V3` and `GND` rails, plus a **$0.1\mu\text{F}$ Ceramic Capacitor** close to the MAX30102 power pins.
3. **MAX30102 Optical Quality**:
   - Keep the optical glass clean.
   - Place finger gently with steady pressure (do not press too hard or blood flow will be occluded).
