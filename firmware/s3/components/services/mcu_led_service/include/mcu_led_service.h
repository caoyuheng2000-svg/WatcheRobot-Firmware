#ifndef MCU_LED_SERVICE_H
#define MCU_LED_SERVICE_H

#include "esp_err.h"

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    MCU_LED_MODE_OFF = 0,
    MCU_LED_MODE_STATIC = 1,
    MCU_LED_MODE_EFFECT = 2,
} mcu_led_mode_t;

typedef struct {
    mcu_led_mode_t mode;
    uint8_t red;
    uint8_t green;
    uint8_t blue;
    uint8_t brightness;
    uint8_t effect_id;
    uint16_t period_ms;
    uint16_t repeat_count;
} mcu_led_request_t;

esp_err_t mcu_led_service_init(void);
esp_err_t mcu_led_submit(const mcu_led_request_t *request);

#ifdef __cplusplus
}
#endif

#endif /* MCU_LED_SERVICE_H */
