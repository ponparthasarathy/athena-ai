"""
======================================================================================
PROJECT: ATHENA — Dual-Head TinyML Engine Trainer & C++ Header Generator for ESP32
AUTHOR:  Principal AI/Embedded Engineer
DESCRIPTION:
  Trains a high-accuracy Dual-Head TinyML Engine for ESP32:
  1. IMU Motion Classification & Fall Detection (50 Hz sliding window)
  2. Environmental Heatwave & Physiological Strain Classifier (T, RH, HI, HR, SpO2)
  Exports optimized, zero-dependency C++ code into TinyML_FallDetector.h.
======================================================================================
"""

import os
import math
import numpy as np
from sklearn.tree import DecisionTreeClassifier, _tree
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

np.random.seed(42)

NUM_SAMPLES_IMU = 1000
WINDOW_SIZE = 64

# Head 1: Motion Classes
IMU_CLASS_NAMES = ["RESTING", "WALKING", "RUNNING", "SENSOR_DROP", "FALL"]

# Head 2: Heatwave Strain Classes
HEAT_CLASS_NAMES = ["HEAT_NORMAL", "HEAT_CAUTION", "HEAT_WARNING", "HEAT_EMERGENCY"]
# 0: Normal (<32C HI), 1: Caution (32-38C HI), 2: Warning (38-41C HI or high HR), 3: Emergency (>41C HI or Heat Stroke HR+HI)


# ======================================================================================
# 1. IMU MOTION DATASET GENERATION
# ======================================================================================
def generate_synthetic_imu_dataset():
    X_features = []
    y_labels = []

    for c_idx, c_name in enumerate(IMU_CLASS_NAMES):
        for _ in range(NUM_SAMPLES_IMU):
            t = np.linspace(0, 1.28, WINDOW_SIZE)
            
            if c_name == "RESTING":
                ax = np.random.normal(0.0, 0.03, WINDOW_SIZE)
                ay = np.random.normal(0.0, 0.03, WINDOW_SIZE)
                az = np.random.normal(1.0, 0.03, WINDOW_SIZE)
                gx = np.random.normal(0.0, 5.0, WINDOW_SIZE)
                gy = np.random.normal(0.0, 5.0, WINDOW_SIZE)
                gz = np.random.normal(0.0, 5.0, WINDOW_SIZE)

            elif c_name == "WALKING":
                freq = np.random.uniform(1.5, 2.0)
                ax = 0.2 * np.sin(2 * np.pi * freq * t) + np.random.normal(0, 0.05, WINDOW_SIZE)
                ay = 0.3 * np.cos(2 * np.pi * freq * t) + np.random.normal(0, 0.05, WINDOW_SIZE)
                az = 1.0 + 0.35 * np.sin(2 * np.pi * freq * t) + np.random.normal(0, 0.05, WINDOW_SIZE)
                gx = 40.0 * np.sin(2 * np.pi * freq * t) + np.random.normal(0, 10, WINDOW_SIZE)
                gy = 30.0 * np.cos(2 * np.pi * freq * t) + np.random.normal(0, 10, WINDOW_SIZE)
                gz = 20.0 * np.sin(2 * np.pi * freq * t) + np.random.normal(0, 5, WINDOW_SIZE)

            elif c_name == "RUNNING":
                freq = np.random.uniform(2.5, 3.5)
                ax = 0.6 * np.sin(2 * np.pi * freq * t) + np.random.normal(0, 0.1, WINDOW_SIZE)
                ay = 0.7 * np.cos(2 * np.pi * freq * t) + np.random.normal(0, 0.1, WINDOW_SIZE)
                az = 1.0 + 0.9 * np.sin(2 * np.pi * freq * t) + np.random.normal(0, 0.15, WINDOW_SIZE)
                gx = 120.0 * np.sin(2 * np.pi * freq * t) + np.random.normal(0, 25, WINDOW_SIZE)
                gy = 100.0 * np.cos(2 * np.pi * freq * t) + np.random.normal(0, 25, WINDOW_SIZE)
                gz = 60.0 * np.sin(2 * np.pi * freq * t) + np.random.normal(0, 15, WINDOW_SIZE)

            elif c_name == "SENSOR_DROP":
                ax = np.random.normal(0.0, 0.05, WINDOW_SIZE)
                ay = np.random.normal(0.0, 0.05, WINDOW_SIZE)
                az = np.random.normal(1.0, 0.05, WINDOW_SIZE)
                gx = np.random.normal(0.0, 10.0, WINDOW_SIZE)
                gy = np.random.normal(0.0, 10.0, WINDOW_SIZE)
                gz = np.random.normal(0.0, 10.0, WINDOW_SIZE)

                ff_idx = range(15, 22)
                ax[ff_idx] *= 0.1
                ay[ff_idx] *= 0.1
                az[ff_idx] *= 0.1

                az[23] = np.random.uniform(3.0, 4.5)
                ax[23] = np.random.uniform(-1.5, 1.5)
                ay[23] = np.random.uniform(-1.5, 1.5)

                post_idx = range(25, WINDOW_SIZE)
                ax[post_idx] += np.random.normal(0.2, 0.3, len(post_idx))
                ay[post_idx] += np.random.normal(0.2, 0.3, len(post_idx))
                gx[post_idx] += np.random.normal(50, 20, len(post_idx))

            elif c_name == "FALL":
                ax = np.random.normal(0.0, 0.05, WINDOW_SIZE)
                ay = np.random.normal(0.0, 0.05, WINDOW_SIZE)
                az = np.random.normal(1.0, 0.05, WINDOW_SIZE)
                gx = np.random.normal(0.0, 10.0, WINDOW_SIZE)
                gy = np.random.normal(0.0, 10.0, WINDOW_SIZE)
                gz = np.random.normal(0.0, 10.0, WINDOW_SIZE)

                ff_idx = range(12, 21)
                ax[ff_idx] = np.random.normal(0.05, 0.05, len(ff_idx))
                ay[ff_idx] = np.random.normal(0.05, 0.05, len(ff_idx))
                az[ff_idx] = np.random.normal(0.1, 0.05, len(ff_idx))

                imp_mag = np.random.uniform(3.2, 5.0)
                az[21] = imp_mag * 0.7
                ax[22] = imp_mag * 0.8
                ay[22] = imp_mag * 0.5
                gx[21:24] = np.random.uniform(200, 450, 3)
                gy[21:24] = np.random.uniform(150, 350, 3)

                post_idx = range(25, WINDOW_SIZE)
                az[post_idx] = np.random.normal(0.15, 0.03, len(post_idx))
                ax[post_idx] = np.random.normal(0.95, 0.03, len(post_idx))
                ay[post_idx] = np.random.normal(0.10, 0.03, len(post_idx))

                gx[post_idx] = np.random.normal(0.0, 3.0, len(post_idx))
                gy[post_idx] = np.random.normal(0.0, 3.0, len(post_idx))
                gz[post_idx] = np.random.normal(0.0, 3.0, len(post_idx))

            accel_mag = np.sqrt(ax**2 + ay**2 + az**2)
            gyro_mag = np.sqrt(gx**2 + gy**2 + gz**2)

            f_mean_mag = np.mean(accel_mag)
            f_min_mag = np.min(accel_mag)
            f_max_mag = np.max(accel_mag)
            f_std_mag = np.std(accel_mag)
            f_max_gyro = np.max(gyro_mag)
            
            init_tilt = math.degrees(math.acos(np.clip(np.mean(az[:10]) / np.mean(accel_mag[:10]), -1.0, 1.0)))
            final_tilt = math.degrees(math.acos(np.clip(np.mean(az[-15:]) / np.mean(accel_mag[-15:]), -1.0, 1.0)))
            f_tilt_delta = abs(final_tilt - init_tilt)
            f_still_var = np.var(accel_mag[-20:])

            X_features.append([
                f_mean_mag, f_min_mag, f_max_mag, f_std_mag,
                f_max_gyro, f_tilt_delta, f_still_var
            ])
            y_labels.append(c_idx)

    return np.array(X_features), np.array(y_labels)


# ======================================================================================
# 2. HEATWAVE & HEAT STRAIN DATASET GENERATION
# ======================================================================================
def compute_heat_index(t_c, rh):
    t_f = t_c * 1.8 + 32.0
    hi_f = (-42.379 + 2.04901523 * t_f + 10.14333127 * rh
            - 0.22475541 * t_f * rh - 0.00683783 * t_f * t_f
            - 0.05481717 * rh * rh + 0.00122874 * t_f * t_f * rh
            + 0.00085282 * t_f * rh * rh - 0.00000199 * t_f * t_f * rh * rh)
    return (hi_f - 32.0) / 1.8


def generate_synthetic_heatwave_dataset(n_samples=2000):
    X_heat = []
    y_heat = []

    for _ in range(n_samples):
        temp_c = np.random.uniform(20.0, 46.0)
        humidity = np.random.uniform(20.0, 95.0)
        heat_index = compute_heat_index(temp_c, humidity)
        heart_rate = np.random.randint(55, 150)
        spo2 = np.random.randint(88, 100)

        # Labels based on clinical NOAA & physiological strain
        if heat_index >= 41.0 or (heat_index >= 38.0 and heart_rate > 120):
            cls = 3 # HEAT_EMERGENCY (Heat Stroke Risk)
        elif heat_index >= 38.0 or (heat_index >= 35.0 and heart_rate > 105):
            cls = 2 # HEAT_WARNING (Severe Heat Stress)
        elif heat_index >= 32.0 or heart_rate > 100:
            cls = 1 # HEAT_CAUTION
        else:
            cls = 0 # HEAT_NORMAL

        X_heat.append([temp_c, humidity, heat_index, float(heart_rate), float(spo2)])
        y_heat.append(cls)

    return np.array(X_heat), np.array(y_heat)


# ======================================================================================
# 3. C++ TREE CODE GENERATORS
# ======================================================================================
def export_decision_tree_to_cpp(tree, func_name, feature_names, class_names):
    tree_ = tree.tree_
    feature_name = [
        feature_names[i] if i != _tree.TREE_UNDEFINED else "undefined!"
        for i in tree_.feature
    ]

    lines = []
    args = ", ".join([f"float {f}" for f in feature_names])
    lines.append(f"inline int {func_name}({args}, float &out_prob) {{")

    def recurse(node, depth):
        indent = "  " * depth
        if tree_.feature[node] != _tree.TREE_UNDEFINED:
            name = feature_name[node]
            threshold = tree_.threshold[node]
            lines.append(f"{indent}if ({name} <= {threshold:.6f}f) {{")
            recurse(tree_.children_left[node], depth + 1)
            lines.append(f"{indent}}} else {{")
            recurse(tree_.children_right[node], depth + 1)
            lines.append(f"{indent}}}")
        else:
            value = tree_.value[node][0]
            total = np.sum(value)
            probs = value / total
            best_class = np.argmax(probs)
            prob = probs[best_class]
            lines.append(f"{indent}out_prob = {prob:.4f}f;")
            lines.append(f"{indent}return {best_class}; // {class_names[best_class]}")

    recurse(0, 1)
    lines.append("}")
    return "\n".join(lines)


def train_and_export():
    print("[TinyML] Generating synthetic 50 Hz IMU time-series dataset...")
    X_imu, y_imu = generate_synthetic_imu_dataset()
    X_train_imu, X_test_imu, y_train_imu, y_test_imu = train_test_split(X_imu, y_imu, test_size=0.25, random_state=42, stratify=y_imu)

    dt_imu = DecisionTreeClassifier(max_depth=7, random_state=42)
    dt_imu.fit(X_train_imu, y_train_imu)
    acc_imu = accuracy_score(y_test_imu, dt_imu.predict(X_test_imu))
    print(f"\n==================================================")
    print(f"   1. TINYML ESP32 IMU MODEL ACCURACY: {acc_imu * 100:.2f}%")
    print(f"==================================================")

    print("\n[TinyML] Generating Heatwave & Heat Strain dataset...")
    X_heat, y_heat = generate_synthetic_heatwave_dataset()
    X_train_h, X_test_h, y_train_h, y_test_h = train_test_split(X_heat, y_heat, test_size=0.25, random_state=42, stratify=y_heat)

    dt_heat = DecisionTreeClassifier(max_depth=6, random_state=42)
    dt_heat.fit(X_train_h, y_train_h)
    acc_heat = accuracy_score(y_test_h, dt_heat.predict(X_test_h))
    print(f"\n==================================================")
    print(f"   2. TINYML ESP32 HEATWAVE MODEL ACCURACY: {acc_heat * 100:.2f}%")
    print(f"==================================================")

    imu_features = ["f_mean_mag", "f_min_mag", "f_max_mag", "f_std_mag", "f_max_gyro", "f_tilt_delta", "f_still_var"]
    heat_features = ["temp_c", "humidity", "heat_index_c", "heart_rate", "spo2"]

    cpp_tree_imu = export_decision_tree_to_cpp(dt_imu, "predictTinyMLClass", imu_features, IMU_CLASS_NAMES)
    cpp_tree_heat = export_decision_tree_to_cpp(dt_heat, "predictTinyMLHeatwaveClass", heat_features, HEAT_CLASS_NAMES)

    header_content = f"""/*
 * ======================================================================================
 * PROJECT: ATHENA — Dual-Head Embedded TinyML Engine for ESP32 (WROOM-32)
 * AUTHOR:  Principal AI & Embedded Systems Engineer
 * 
 * DESCRIPTION:
 *   1. IMU Motion Classifier & Fall Detector (50 Hz sliding window, Acc: {acc_imu * 100:.1f}%)
 *   2. Heatwave & Thermal Stress Risk Classifier (T, RH, HI, HR, Acc: {acc_heat * 100:.1f}%)
 * ======================================================================================
 */

#ifndef TINYML_FALL_DETECTOR_H
#define TINYML_FALL_DETECTOR_H

#include <Arduino.h>
#include <math.h>

#define TINYML_WINDOW_SIZE 64

enum TinyMLMotionClass {{
  TINYML_CLASS_RESTING = 0,
  TINYML_CLASS_WALKING = 1,
  TINYML_CLASS_RUNNING = 2,
  TINYML_CLASS_SENSOR_DROP = 3,
  TINYML_CLASS_FALL = 4
}};

enum TinyMLHeatClass {{
  TINYML_HEAT_NORMAL = 0,
  TINYML_HEAT_CAUTION = 1,
  TINYML_HEAT_WARNING = 2,
  TINYML_HEAT_EMERGENCY = 3
}};

class TinyMLFallDetector {{
private:
  float ax_buf[TINYML_WINDOW_SIZE];
  float ay_buf[TINYML_WINDOW_SIZE];
  float az_buf[TINYML_WINDOW_SIZE];
  float gx_buf[TINYML_WINDOW_SIZE];
  float gy_buf[TINYML_WINDOW_SIZE];
  float gz_buf[TINYML_WINDOW_SIZE];
  
  uint16_t buf_index;
  bool buf_full;

  TinyMLMotionClass current_class;
  float current_probability;
  float current_fall_prob;

  TinyMLHeatClass current_heat_class;
  float current_heat_prob;

{cpp_tree_imu}

{cpp_tree_heat}

public:
  TinyMLFallDetector() : buf_index(0), buf_full(false), 
                         current_class(TINYML_CLASS_RESTING), current_probability(0.99f), current_fall_prob(0.0f),
                         current_heat_class(TINYML_HEAT_NORMAL), current_heat_prob(0.99f) {{
    for (int i = 0; i < TINYML_WINDOW_SIZE; i++) {{
      ax_buf[i] = 0.0f; ay_buf[i] = 0.0f; az_buf[i] = 1.0f;
      gx_buf[i] = 0.0f; gy_buf[i] = 0.0f; gz_buf[i] = 0.0f;
    }}
  }}

  void addSample(float ax_g, float ay_g, float az_g, float gx_deg, float gy_deg, float gz_deg) {{
    ax_buf[buf_index] = ax_g;
    ay_buf[buf_index] = ay_g;
    az_buf[buf_index] = az_g;
    gx_buf[buf_index] = gx_deg;
    gy_buf[buf_index] = gy_deg;
    gz_buf[buf_index] = gz_deg;

    buf_index = (buf_index + 1) % TINYML_WINDOW_SIZE;
    if (buf_index == 0) buf_full = true;
  }}

  bool isReady() const {{ return buf_full; }}

  void updateInference() {{
    if (!buf_full) return;

    float sum_mag = 0.0f, min_mag = 999.0f, max_mag = 0.0f, max_gyro = 0.0f;
    float accel_mags[TINYML_WINDOW_SIZE];

    for (int i = 0; i < TINYML_WINDOW_SIZE; i++) {{
      float mag = sqrt(ax_buf[i]*ax_buf[i] + ay_buf[i]*ay_buf[i] + az_buf[i]*az_buf[i]);
      float gmag = sqrt(gx_buf[i]*gx_buf[i] + gy_buf[i]*gy_buf[i] + gz_buf[i]*gz_buf[i]);
      accel_mags[i] = mag;
      sum_mag += mag;
      if (mag < min_mag) min_mag = mag;
      if (mag > max_mag) max_mag = mag;
      if (gmag > max_gyro) max_gyro = gmag;
    }}

    float mean_mag = sum_mag / TINYML_WINDOW_SIZE;

    float var_sum = 0.0f;
    for (int i = 0; i < TINYML_WINDOW_SIZE; i++) {{
      float d = accel_mags[i] - mean_mag;
      var_sum += d * d;
    }}
    float std_mag = sqrt(var_sum / TINYML_WINDOW_SIZE);

    float init_az = 0.0f, final_az = 0.0f, init_m = 0.0f, final_m = 0.0f;
    for (int i = 0; i < 10; i++) {{ init_az += az_buf[i]; init_m += accel_mags[i]; }}
    for (int i = TINYML_WINDOW_SIZE - 15; i < TINYML_WINDOW_SIZE; i++) {{ final_az += az_buf[i]; final_m += accel_mags[i]; }}

    float init_tilt = acos(constrain((init_az/10.0f)/(init_m/10.0f), -1.0f, 1.0f)) * 57.2958f;
    float final_tilt = acos(constrain((final_az/15.0f)/(final_m/15.0f), -1.0f, 1.0f)) * 57.2958f;
    float tilt_delta = fabs(final_tilt - init_tilt);

    float last20_m = 0.0f;
    for (int i = TINYML_WINDOW_SIZE - 20; i < TINYML_WINDOW_SIZE; i++) last20_m += accel_mags[i];
    last20_m /= 20.0f;

    float last20_v = 0.0f;
    for (int i = TINYML_WINDOW_SIZE - 20; i < TINYML_WINDOW_SIZE; i++) {{
      float d = accel_mags[i] - last20_m;
      last20_v += d * d;
    }}
    float stillness_var = last20_v / 20.0f;

    float out_prob = 0.0f;
    int predicted_cls = predictTinyMLClass(mean_mag, min_mag, max_mag, std_mag, max_gyro, tilt_delta, stillness_var, out_prob);
    current_class = (TinyMLMotionClass)predicted_cls;
    current_probability = out_prob;

    if (current_class == TINYML_CLASS_FALL) current_fall_prob = out_prob;
    else if (current_class == TINYML_CLASS_SENSOR_DROP) current_fall_prob = 0.15f;
    else current_fall_prob = 0.01f;
  }}

  void updateHeatwaveInference(float temp_c, float humidity, float heat_index_c, float heart_rate, float spo2) {{
    float out_prob = 0.0f;
    int predicted_cls = predictTinyMLHeatwaveClass(temp_c, humidity, heat_index_c, heart_rate, spo2, out_prob);
    current_heat_class = (TinyMLHeatClass)predicted_cls;
    current_heat_prob = out_prob;
  }}

  TinyMLMotionClass getClass() const {{ return current_class; }}
  float getProbability() const {{ return current_probability; }}
  float getFallProbability() const {{ return current_fall_prob; }}
  
  TinyMLHeatClass getHeatClass() const {{ return current_heat_class; }}
  float getHeatProbability() const {{ return current_heat_prob; }}

  float getAccuracyMetric() const {{ return {acc_imu * 100:.1f}f; }}

  const char* getClassString() const {{
    switch (current_class) {{
      case TINYML_CLASS_RESTING:     return "RESTING";
      case TINYML_CLASS_WALKING:     return "WALKING";
      case TINYML_CLASS_RUNNING:     return "RUNNING";
      case TINYML_CLASS_SENSOR_DROP: return "SENSOR_DROP";
      case TINYML_CLASS_FALL:        return "FALL_DETECTED";
      default:                       return "UNKNOWN";
    }}
  }}

  const char* getHeatClassString() const {{
    switch (current_heat_class) {{
      case TINYML_HEAT_NORMAL:    return "HEAT_NORMAL";
      case TINYML_HEAT_CAUTION:   return "HEAT_CAUTION";
      case TINYML_HEAT_WARNING:   return "HEAT_WARNING";
      case TINYML_HEAT_EMERGENCY: return "HEAT_EMERGENCY";
      default:                    return "NORMAL";
    }}
  }}
}};

#endif // TINYML_FALL_DETECTOR_H
"""

    header_path = os.path.join(os.path.dirname(__file__), "sahaay_firmware", "TinyML_FallDetector.h")
    with open(header_path, "w") as f:
        f.write(header_content)
    
    print(f"[TinyML] Dual-Head C++ Header generated successfully -> {header_path}")


if __name__ == "__main__":
    train_and_export()
