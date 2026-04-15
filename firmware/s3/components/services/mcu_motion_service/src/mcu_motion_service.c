#include "mcu_motion_service.h"

#include <stdbool.h>
#include <string.h>

static mcu_motion_request_t s_last_request;
static bool s_has_last_request;

static bool mcu_motion_request_is_valid(const mcu_motion_request_t *request)
{
    if (request == NULL) {
        return false;
    }

    if (request->axis_mask == 0U) {
        return false;
    }

    if ((request->axis_mask & ~(MCU_MOTION_AXIS_X | MCU_MOTION_AXIS_Y)) != 0U) {
        return false;
    }

    if (request->duration_ms == 0U) {
        return false;
    }

    if (request->motion_profile != MCU_MOTION_PROFILE_LINEAR) {
        return false;
    }

    if (request->source < MCU_MOTION_SOURCE_UNKNOWN || request->source > MCU_MOTION_SOURCE_RECOVERY) {
        return false;
    }

    return true;
}

esp_err_t mcu_motion_service_init(void)
{
    memset(&s_last_request, 0, sizeof(s_last_request));
    s_has_last_request = false;
    return ESP_OK;
}

esp_err_t mcu_motion_submit(const mcu_motion_request_t *request)
{
    if (!mcu_motion_request_is_valid(request)) {
        return ESP_ERR_INVALID_ARG;
    }

    s_last_request = *request;
    s_has_last_request = true;
    return ESP_OK;
}

esp_err_t mcu_motion_service_get_last_request(mcu_motion_request_t *out_request)
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

esp_err_t mcu_motion_stop(mcu_motion_source_t source)
{
    if (source < MCU_MOTION_SOURCE_UNKNOWN || source > MCU_MOTION_SOURCE_RECOVERY) {
        return ESP_ERR_INVALID_ARG;
    }

    return ESP_OK;
}
