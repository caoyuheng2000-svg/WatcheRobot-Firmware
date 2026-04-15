#ifndef MCU_MOTION_SERVICE_H
#define MCU_MOTION_SERVICE_H

#include "esp_err.h"

#include <stdbool.h>
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
    MCU_MOTION_STOP_CURRENT = 0,
    MCU_MOTION_STOP_ALL_PENDING = 1,
} mcu_motion_stop_scope_t;

typedef struct {
    bool has_x;
    bool has_y;
    int16_t x_deg;
    int16_t y_deg;
    uint16_t duration_ms;
    mcu_motion_source_t source;
} mcu_motion_request_t;

typedef struct {
    mcu_motion_stop_scope_t scope;
    mcu_motion_source_t source;
} mcu_motion_stop_request_t;

esp_err_t mcu_motion_service_init(void);
esp_err_t mcu_motion_submit(const mcu_motion_request_t *request);
esp_err_t mcu_motion_stop(const mcu_motion_stop_request_t *request);

#ifdef __cplusplus
}
#endif

#endif /* MCU_MOTION_SERVICE_H */
