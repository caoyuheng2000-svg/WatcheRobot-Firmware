#include "mcu_led_service.h"

esp_err_t mcu_led_service_init(void)
{
    return ESP_OK;
}

esp_err_t mcu_led_submit(const mcu_led_request_t *request)
{
    if (request == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    return ESP_ERR_NOT_SUPPORTED;
}
