#ifndef MCU_SENSOR_SERVICE_H
#define MCU_SENSOR_SERVICE_H

#include "esp_err.h"

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    bool active;
    uint32_t timestamp_ms;
} mcu_touch_state_t;

typedef struct {
    uint16_t heading_deg_x100;
    uint16_t field_norm_uT;
    uint8_t quality;
    uint8_t status_bits;
    uint32_t timestamp_ms;
} mcu_mag_state_t;

typedef struct {
    int16_t roll_deg_x100;
    int16_t pitch_deg_x100;
    int16_t yaw_deg_x100;
    uint16_t acc_norm_mg;
    uint16_t gyro_norm_dps_x10;
    uint8_t motion_flags;
    uint32_t timestamp_ms;
} mcu_imu_state_t;

esp_err_t mcu_sensor_service_init(void);
esp_err_t mcu_sensor_service_get_latest_touch(mcu_touch_state_t *out_state);
esp_err_t mcu_sensor_service_get_latest_mag(mcu_mag_state_t *out_state);
esp_err_t mcu_sensor_service_get_latest_imu(mcu_imu_state_t *out_state);

#ifdef __cplusplus
}
#endif

#endif /* MCU_SENSOR_SERVICE_H */
