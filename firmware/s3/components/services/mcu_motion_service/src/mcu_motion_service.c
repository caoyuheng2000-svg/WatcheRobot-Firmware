#include "mcu_motion_service.h"

esp_err_t mcu_motion_service_init(void)
{
    return ESP_OK;
}

esp_err_t mcu_motion_submit(const mcu_motion_request_t *request)
{
    if (request == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t mcu_motion_stop(const mcu_motion_stop_request_t *request)
{
    if (request == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    return ESP_ERR_NOT_SUPPORTED;
}
