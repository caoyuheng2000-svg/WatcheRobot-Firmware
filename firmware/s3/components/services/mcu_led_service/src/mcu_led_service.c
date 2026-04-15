#include "mcu_led_service.h"

#include <stdbool.h>

static mcu_led_request_t s_last_request;
static bool s_has_last_request;

static bool mcu_led_request_is_valid(const mcu_led_request_t *request)
{
    if (request == NULL) {
        return false;
    }

    if (request->mode > MCU_LED_MODE_EFFECT) {
        return false;
    }

    if (request->mode == MCU_LED_MODE_EFFECT) {
        if (request->effect_id < MCU_LED_EFFECT_BLINK ||
            request->effect_id > MCU_LED_EFFECT_STATUS_PULSE) {
            return false;
        }

        if (request->period_ms == 0U) {
            return false;
        }
    }

    return true;
}

esp_err_t mcu_led_service_init(void)
{
    s_last_request = (mcu_led_request_t){0};
    s_has_last_request = false;
    return ESP_OK;
}

esp_err_t mcu_led_submit(const mcu_led_request_t *request)
{
    if (!mcu_led_request_is_valid(request)) {
        return ESP_ERR_INVALID_ARG;
    }

    s_last_request = *request;
    s_has_last_request = true;
    return ESP_OK;
}

esp_err_t mcu_led_service_get_last_request(mcu_led_request_t *out_request)
{
    if (out_request == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_has_last_request) {
        return ESP_ERR_NOT_FOUND;
    }

    *out_request = s_last_request;
    return ESP_OK;
}
