#ifndef MCU_MOTION_SERVICE_H
#define MCU_MOTION_SERVICE_H

#include "esp_err.h"

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    MCU_MOTION_SOURCE_UNKNOWN = 0,
    MCU_MOTION_SOURCE_BEHAVIOR = 1,
    MCU_MOTION_SOURCE_BLE = 2,
    MCU_MOTION_SOURCE_WS = 3,
    MCU_MOTION_SOURCE_RECOVERY = 4,
} mcu_motion_source_t;

typedef enum {
    MCU_MOTION_PROFILE_LINEAR = 0,
} mcu_motion_profile_t;

typedef enum {
    MCU_MOTION_AXIS_X = 1u << 0,
    MCU_MOTION_AXIS_Y = 1u << 1,
} mcu_motion_axis_t;

typedef struct {
    uint8_t axis_mask;
    int16_t x_deg_x10;
    int16_t y_deg_x10;
    uint16_t duration_ms;
    uint8_t motion_profile;
    mcu_motion_source_t source;
} mcu_motion_request_t;

esp_err_t mcu_motion_service_init(void);
esp_err_t mcu_motion_submit(const mcu_motion_request_t *request);
esp_err_t mcu_motion_service_get_last_request(mcu_motion_request_t *out_request);
esp_err_t mcu_motion_stop(mcu_motion_source_t source);

#ifdef __cplusplus
}
#endif

#endif /* MCU_MOTION_SERVICE_H */
