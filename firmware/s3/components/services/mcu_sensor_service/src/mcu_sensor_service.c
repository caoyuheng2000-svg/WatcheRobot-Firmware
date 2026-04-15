#include "mcu_sensor_service.h"

#include <string.h>

typedef struct {
    bool touch_valid;
    bool mag_valid;
    bool imu_valid;
    mcu_touch_state_t touch;
    mcu_mag_state_t mag;
    mcu_imu_state_t imu;
    mcu_sensor_service_stats_t stats;
} mcu_sensor_cache_t;

static mcu_sensor_cache_t s_cache;

esp_err_t mcu_sensor_service_init(void)
{
    memset(&s_cache, 0, sizeof(s_cache));
    return ESP_OK;
}

static esp_err_t mcu_sensor_service_apply_touch_impl(const mcu_touch_state_t *state)
{
    if (state == NULL) {
        s_cache.stats.touch_invalid_count++;
        return ESP_ERR_INVALID_ARG;
    }

    if (s_cache.touch_valid) {
        s_cache.stats.touch_overwrite_count++;
    }

    s_cache.touch = *state;
    s_cache.touch_valid = true;
    s_cache.stats.touch_apply_count++;
    return ESP_OK;
}

static esp_err_t mcu_sensor_service_apply_mag_impl(const mcu_mag_state_t *state)
{
    if (state == NULL) {
        s_cache.stats.mag_invalid_count++;
        return ESP_ERR_INVALID_ARG;
    }

    if (s_cache.mag_valid) {
        s_cache.stats.mag_overwrite_count++;
    }

    s_cache.mag = *state;
    s_cache.mag_valid = true;
    s_cache.stats.mag_apply_count++;
    return ESP_OK;
}

static esp_err_t mcu_sensor_service_apply_imu_impl(const mcu_imu_state_t *state)
{
    if (state == NULL) {
        s_cache.stats.imu_invalid_count++;
        return ESP_ERR_INVALID_ARG;
    }

    if (s_cache.imu_valid) {
        s_cache.stats.imu_overwrite_count++;
    }

    s_cache.imu = *state;
    s_cache.imu_valid = true;
    s_cache.stats.imu_apply_count++;
    return ESP_OK;
}

esp_err_t mcu_sensor_service_apply_touch(const mcu_touch_state_t *state)
{
    return mcu_sensor_service_apply_touch_impl(state);
}

esp_err_t mcu_sensor_service_apply_mag(const mcu_mag_state_t *state)
{
    return mcu_sensor_service_apply_mag_impl(state);
}

esp_err_t mcu_sensor_service_apply_imu(const mcu_imu_state_t *state)
{
    return mcu_sensor_service_apply_imu_impl(state);
}

esp_err_t mcu_sensor_service_apply_frame(const mcu_sensor_frame_t *frame)
{
    if (frame == NULL) {
        s_cache.stats.frame_invalid_count++;
        return ESP_ERR_INVALID_ARG;
    }

    s_cache.stats.frame_apply_count++;

    switch (frame->type) {
    case MCU_SENSOR_FRAME_TOUCH:
        return mcu_sensor_service_apply_touch_impl(&frame->data.touch);
    case MCU_SENSOR_FRAME_MAG:
        return mcu_sensor_service_apply_mag_impl(&frame->data.mag);
    case MCU_SENSOR_FRAME_IMU:
        return mcu_sensor_service_apply_imu_impl(&frame->data.imu);
    default:
        s_cache.stats.frame_invalid_count++;
        return ESP_ERR_INVALID_ARG;
    }
}

esp_err_t mcu_sensor_service_update_touch(const mcu_touch_state_t *state)
{
    return mcu_sensor_service_apply_touch(state);
}

esp_err_t mcu_sensor_service_update_mag(const mcu_mag_state_t *state)
{
    return mcu_sensor_service_apply_mag(state);
}

esp_err_t mcu_sensor_service_update_imu(const mcu_imu_state_t *state)
{
    return mcu_sensor_service_apply_imu(state);
}

esp_err_t mcu_sensor_service_get_latest_touch(mcu_touch_state_t *out_state)
{
    if (out_state == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    *out_state = s_cache.touch;
    return ESP_OK;
}

esp_err_t mcu_sensor_service_get_latest_mag(mcu_mag_state_t *out_state)
{
    if (out_state == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    *out_state = s_cache.mag;
    return ESP_OK;
}

esp_err_t mcu_sensor_service_get_latest_imu(mcu_imu_state_t *out_state)
{
    if (out_state == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    *out_state = s_cache.imu;
    return ESP_OK;
}

bool mcu_sensor_service_has_latest_touch(void)
{
    return s_cache.touch_valid;
}

bool mcu_sensor_service_has_latest_mag(void)
{
    return s_cache.mag_valid;
}

bool mcu_sensor_service_has_latest_imu(void)
{
    return s_cache.imu_valid;
}

esp_err_t mcu_sensor_service_get_stats(mcu_sensor_service_stats_t *out_stats)
{
    if (out_stats == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    *out_stats = s_cache.stats;
    return ESP_OK;
}
