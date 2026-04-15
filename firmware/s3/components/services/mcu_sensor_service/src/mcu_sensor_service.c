#include "mcu_sensor_service.h"

#include <string.h>

static mcu_touch_state_t s_touch_state;
static mcu_mag_state_t s_mag_state;
static mcu_imu_state_t s_imu_state;

esp_err_t mcu_sensor_service_init(void)
{
    memset(&s_touch_state, 0, sizeof(s_touch_state));
    memset(&s_mag_state, 0, sizeof(s_mag_state));
    memset(&s_imu_state, 0, sizeof(s_imu_state));
    return ESP_OK;
}

esp_err_t mcu_sensor_service_get_latest_touch(mcu_touch_state_t *out_state)
{
    if (out_state == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    *out_state = s_touch_state;
    return ESP_OK;
}

esp_err_t mcu_sensor_service_get_latest_mag(mcu_mag_state_t *out_state)
{
    if (out_state == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    *out_state = s_mag_state;
    return ESP_OK;
}

esp_err_t mcu_sensor_service_get_latest_imu(mcu_imu_state_t *out_state)
{
    if (out_state == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    *out_state = s_imu_state;
    return ESP_OK;
}
