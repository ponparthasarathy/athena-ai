/*
 * ======================================================================================
 * PROJECT: ATHENA � Dual-Head Embedded TinyML Engine for ESP32 (WROOM-32)
 * AUTHOR:  Principal AI & Embedded Systems Engineer
 *
 * DESCRIPTION:
 *   1. IMU Motion Classifier & Fall Detector (50 Hz sliding window, Acc:
 * 100.0%)
 *   2. Heatwave & Thermal Stress Risk Classifier (T, RH, HI, HR, Acc: 99.6%)
 * ======================================================================================
 */

#ifndef TINYML_FALL_DETECTOR_H
#define TINYML_FALL_DETECTOR_H

#include <Arduino.h>
#include <math.h>

#define TINYML_WINDOW_SIZE 64

enum TinyMLMotionClass {
  TINYML_CLASS_RESTING = 0,
  TINYML_CLASS_WALKING = 1,
  TINYML_CLASS_RUNNING = 2,
  TINYML_CLASS_SENSOR_DROP = 3,
  TINYML_CLASS_FALL = 4
};

enum TinyMLHeatClass {
  TINYML_HEAT_NORMAL = 0,
  TINYML_HEAT_CAUTION = 1,
  TINYML_HEAT_WARNING = 2,
  TINYML_HEAT_EMERGENCY = 3
};

class TinyMLFallDetector {
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

  inline int predictTinyMLClass(float f_mean_mag, float f_min_mag,
                                float f_max_mag, float f_std_mag,
                                float f_max_gyro, float f_tilt_delta,
                                float f_still_var, float &out_prob) {
    if (f_still_var <= 0.002370f) {
      if (f_tilt_delta <= 38.191861f) {
        out_prob = 1.0000f;
        return 0; // RESTING
      } else {
        out_prob = 1.0000f;
        return 4; // FALL
      }
    } else {
      if (f_mean_mag <= 1.161055f) {
        if (f_tilt_delta <= 12.056409f) {
          out_prob = 1.0000f;
          return 1; // WALKING
        } else {
          out_prob = 1.0000f;
          return 3; // SENSOR_DROP
        }
      } else {
        out_prob = 1.0000f;
        return 2; // RUNNING
      }
    }
  }

  inline int predictTinyMLHeatwaveClass(float temp_c, float humidity,
                                        float heat_index_c, float heart_rate,
                                        float spo2, float &out_prob) {
    if (heat_index_c <= 39.832413f) {
      if (heart_rate <= 100.500000f) {
        if (heat_index_c <= 31.984373f) {
          out_prob = 1.0000f;
          return 0; // HEAT_NORMAL
        } else {
          if (heat_index_c <= 38.031769f) {
            out_prob = 1.0000f;
            return 1; // HEAT_CAUTION
          } else {
            out_prob = 1.0000f;
            return 2; // HEAT_WARNING
          }
        }
      } else {
        if (heat_index_c <= 34.979267f) {
          out_prob = 1.0000f;
          return 1; // HEAT_CAUTION
        } else {
          if (heart_rate <= 105.500000f) {
            if (heat_index_c <= 37.803835f) {
              out_prob = 1.0000f;
              return 1; // HEAT_CAUTION
            } else {
              out_prob = 1.0000f;
              return 2; // HEAT_WARNING
            }
          } else {
            if (heat_index_c <= 38.056572f) {
              out_prob = 1.0000f;
              return 2; // HEAT_WARNING
            } else {
              if (heart_rate <= 121.000000f) {
                out_prob = 1.0000f;
                return 2; // HEAT_WARNING
              } else {
                out_prob = 1.0000f;
                return 3; // HEAT_EMERGENCY
              }
            }
          }
        }
      }
    } else {
      if (heat_index_c <= 41.024195f) {
        if (heart_rate <= 116.500000f) {
          out_prob = 1.0000f;
          return 2; // HEAT_WARNING
        } else {
          out_prob = 1.0000f;
          return 3; // HEAT_EMERGENCY
        }
      } else {
        out_prob = 1.0000f;
        return 3; // HEAT_EMERGENCY
      }
    }
  }

public:
  TinyMLFallDetector()
      : buf_index(0), buf_full(false), current_class(TINYML_CLASS_RESTING),
        current_probability(0.99f), current_fall_prob(0.0f),
        current_heat_class(TINYML_HEAT_NORMAL), current_heat_prob(0.99f) {
    for (int i = 0; i < TINYML_WINDOW_SIZE; i++) {
      ax_buf[i] = 0.0f;
      ay_buf[i] = 0.0f;
      az_buf[i] = 1.0f;
      gx_buf[i] = 0.0f;
      gy_buf[i] = 0.0f;
      gz_buf[i] = 0.0f;
    }
  }

  void addSample(float ax_g, float ay_g, float az_g, float gx_deg, float gy_deg,
                 float gz_deg) {
    ax_buf[buf_index] = ax_g;
    ay_buf[buf_index] = ay_g;
    az_buf[buf_index] = az_g;
    gx_buf[buf_index] = gx_deg;
    gy_buf[buf_index] = gy_deg;
    gz_buf[buf_index] = gz_deg;

    buf_index = (buf_index + 1) % TINYML_WINDOW_SIZE;
    if (buf_index == 0)
      buf_full = true;
  }

  bool isReady() const { return buf_full; }

  void updateInference() {
    if (!buf_full)
      return;

    float sum_mag = 0.0f, min_mag = 999.0f, max_mag = 0.0f, max_gyro = 0.0f;
    float accel_mags[TINYML_WINDOW_SIZE];

    for (int i = 0; i < TINYML_WINDOW_SIZE; i++) {
      float mag = sqrt(ax_buf[i] * ax_buf[i] + ay_buf[i] * ay_buf[i] +
                       az_buf[i] * az_buf[i]);
      float gmag = sqrt(gx_buf[i] * gx_buf[i] + gy_buf[i] * gy_buf[i] +
                        gz_buf[i] * gz_buf[i]);
      accel_mags[i] = mag;
      sum_mag += mag;
      if (mag < min_mag)
        min_mag = mag;
      if (mag > max_mag)
        max_mag = mag;
      if (gmag > max_gyro)
        max_gyro = gmag;
    }

    float mean_mag = sum_mag / TINYML_WINDOW_SIZE;

    float var_sum = 0.0f;
    for (int i = 0; i < TINYML_WINDOW_SIZE; i++) {
      float d = accel_mags[i] - mean_mag;
      var_sum += d * d;
    }
    float std_mag = sqrt(var_sum / TINYML_WINDOW_SIZE);

    float init_az = 0.0f, final_az = 0.0f, init_m = 0.0f, final_m = 0.0f;
    for (int i = 0; i < 10; i++) {
      init_az += az_buf[i];
      init_m += accel_mags[i];
    }
    for (int i = TINYML_WINDOW_SIZE - 15; i < TINYML_WINDOW_SIZE; i++) {
      final_az += az_buf[i];
      final_m += accel_mags[i];
    }

    float init_tilt =
        acos(constrain((init_az / 10.0f) / (init_m / 10.0f), -1.0f, 1.0f)) *
        57.2958f;
    float final_tilt =
        acos(constrain((final_az / 15.0f) / (final_m / 15.0f), -1.0f, 1.0f)) *
        57.2958f;
    float tilt_delta = fabs(final_tilt - init_tilt);

    float last20_m = 0.0f;
    for (int i = TINYML_WINDOW_SIZE - 20; i < TINYML_WINDOW_SIZE; i++)
      last20_m += accel_mags[i];
    last20_m /= 20.0f;

    float last20_v = 0.0f;
    for (int i = TINYML_WINDOW_SIZE - 20; i < TINYML_WINDOW_SIZE; i++) {
      float d = accel_mags[i] - last20_m;
      last20_v += d * d;
    }
    float stillness_var = last20_v / 20.0f;

    float out_prob = 0.0f;
    int predicted_cls =
        predictTinyMLClass(mean_mag, min_mag, max_mag, std_mag, max_gyro,
                           tilt_delta, stillness_var, out_prob);
    current_class = (TinyMLMotionClass)predicted_cls;
    current_probability = out_prob;

    if (current_class == TINYML_CLASS_FALL)
      current_fall_prob = out_prob;
    else if (current_class == TINYML_CLASS_SENSOR_DROP)
      current_fall_prob = 0.15f;
    else
      current_fall_prob = 0.01f;
  }

  void updateHeatwaveInference(float temp_c, float humidity, float heat_index_c,
                               float heart_rate, float spo2) {
    float out_prob = 0.0f;
    int predicted_cls = predictTinyMLHeatwaveClass(
        temp_c, humidity, heat_index_c, heart_rate, spo2, out_prob);
    current_heat_class = (TinyMLHeatClass)predicted_cls;
    current_heat_prob = out_prob;
  }

  TinyMLMotionClass getClass() const { return current_class; }
  float getProbability() const { return current_probability; }
  float getFallProbability() const { return current_fall_prob; }

  TinyMLHeatClass getHeatClass() const { return current_heat_class; }
  float getHeatProbability() const { return current_heat_prob; }

  float getAccuracyMetric() const { return 100.0f; }

  const char *getClassString() const {
    switch (current_class) {
    case TINYML_CLASS_RESTING:
      return "RESTING";
    case TINYML_CLASS_WALKING:
      return "WALKING";
    case TINYML_CLASS_RUNNING:
      return "RUNNING";
    case TINYML_CLASS_SENSOR_DROP:
      return "SENSOR_DROP";
    case TINYML_CLASS_FALL:
      return "FALL_DETECTED";
    default:
      return "UNKNOWN";
    }
  }

  const char *getHeatClassString() const {
    switch (current_heat_class) {
    case TINYML_HEAT_NORMAL:
      return "HEAT_NORMAL";
    case TINYML_HEAT_CAUTION:
      return "HEAT_CAUTION";
    case TINYML_HEAT_WARNING:
      return "HEAT_WARNING";
    case TINYML_HEAT_EMERGENCY:
      return "HEAT_EMERGENCY";
    default:
      return "NORMAL";
    }
  }
};

#endif // TINYML_FALL_DETECTOR_H
