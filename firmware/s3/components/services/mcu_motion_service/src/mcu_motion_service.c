#include "mcu_motion_service.h"

#include "esp_log.h"
#include "mcu_link_bootstrap.h"

#include <stdbool.h>
#include <string.h>

static const char *TAG = "MCU_MOTION";
#if !defined(WATCHER_STRESS_BUILD) && !defined(CONFIG_WATCHER_STRESS_BUILD)
static const char *OBS_TAG = "MCU_OBS";
#endif

static mcu_motion_request_t s_last_request;
static bool s_has_last_request;
static uint32_t s_last_command_seq;
static bool s_command_inflight;

static uint16_t decode_u16_le(const uint8_t *src)
{
    return (uint16_t)(((uint16_t)src[0]) | ((uint16_t)src[1] << 8u));
}

static uint32_t decode_u32_le(const uint8_t *src)
{
    return ((uint32_t)src[0]) | ((uint32_t)src[1] << 8u) | ((uint32_t)src[2] << 16u) | ((uint32_t)src[3] << 24u);
}

#if !defined(WATCHER_STRESS_BUILD) && !defined(CONFIG_WATCHER_STRESS_BUILD)
static int16_t decode_i16_le(const uint8_t *src)
{
    return (int16_t)decode_u16_le(src);
}
#endif

static void encode_u16_le(uint8_t *dst, uint16_t value)
{
    dst[0] = (uint8_t)(value & 0xFFu);
    dst[1] = (uint8_t)((value >> 8) & 0xFFu);
}

static void encode_i16_le(uint8_t *dst, int16_t value)
{
    encode_u16_le(dst, (uint16_t)value);
}

static esp_err_t mcu_motion_submit_runtime_frame(const mcu_motion_request_t *request, uint32_t *out_seq)
{
    uint8_t payload[9];
    mcu_link_t *link;
    uint32_t seq = 0u;
    size_t wire_len = 0u;
    esp_err_t ret;

    if (request == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    link = mcu_link_bootstrap_get_link();
    if (link == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    if (!mcu_link_bootstrap_is_ready()) {
        ESP_LOGW(TAG, "MCU link not fully ready; rejecting motion request");
        return ESP_ERR_INVALID_STATE;
    }

    payload[0] = request->axis_mask;
    encode_i16_le(&payload[1], request->x_deg_x10);
    encode_i16_le(&payload[3], request->y_deg_x10);
    encode_u16_le(&payload[5], request->duration_ms);
    payload[7] = request->motion_profile;
    payload[8] = (uint8_t)request->source;

    ret = mcu_link_send_frame(link, MCU_FRAME_CLASS_MOTION, MCU_MOTION_MSG_SERVO_MOVE, MCU_FRAME_FLAG_ACK_REQ,
                              payload, (uint16_t)sizeof(payload), &seq, &wire_len);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Failed to queue SERVO_MOVE frame: %s", esp_err_to_name(ret));
        return ret;
    }

#if !defined(WATCHER_STRESS_BUILD) && !defined(CONFIG_WATCHER_STRESS_BUILD)
    ESP_LOGI(TAG, "Queued SERVO_MOVE frame seq=%lu wire_len=%u axis_mask=0x%02x duration_ms=%u",
             (unsigned long)seq, (unsigned)wire_len, request->axis_mask, (unsigned)request->duration_ms);
#endif
    s_last_command_seq = seq;
    s_command_inflight = true;
    if (out_seq != NULL) {
        *out_seq = seq;
    }
    return ESP_OK;
}

static esp_err_t mcu_motion_submit_stop_frame(mcu_motion_source_t source)
{
    uint8_t payload[2];
    mcu_link_t *link;
    uint32_t seq = 0u;
    size_t wire_len = 0u;
    esp_err_t ret;

    link = mcu_link_bootstrap_get_link();
    if (link == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    if (!mcu_link_bootstrap_is_ready()) {
        ESP_LOGW(TAG, "MCU link not fully ready; rejecting stop request");
        return ESP_ERR_INVALID_STATE;
    }

    payload[0] = 0u; /* current_motion */
    payload[1] = (uint8_t)source;
    ret = mcu_link_send_frame(link, MCU_FRAME_CLASS_MOTION, MCU_MOTION_MSG_SERVO_STOP, MCU_FRAME_FLAG_ACK_REQ,
                              payload, (uint16_t)sizeof(payload), &seq, &wire_len);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Failed to queue SERVO_STOP frame: %s", esp_err_to_name(ret));
        return ret;
    }

#if !defined(WATCHER_STRESS_BUILD) && !defined(CONFIG_WATCHER_STRESS_BUILD)
    ESP_LOGI(TAG, "Queued SERVO_STOP frame seq=%lu wire_len=%u source=%u", (unsigned long)seq, (unsigned)wire_len,
             (unsigned)source);
#endif
    s_last_command_seq = seq;
    s_command_inflight = true;
    return ESP_OK;
}

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
    s_last_command_seq = 0u;
    s_command_inflight = false;
    return ESP_OK;
}

esp_err_t mcu_motion_submit(const mcu_motion_request_t *request)
{
    return mcu_motion_submit_with_seq(request, NULL);
}

esp_err_t mcu_motion_submit_with_seq(const mcu_motion_request_t *request, uint32_t *out_seq)
{
    if (!mcu_motion_request_is_valid(request)) {
        return ESP_ERR_INVALID_ARG;
    }

    {
        esp_err_t ret = mcu_motion_submit_runtime_frame(request, out_seq);
        if (ret != ESP_OK) {
            return ret;
        }

        s_last_request = *request;
        s_has_last_request = true;
        return ESP_OK;
    }
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

    return mcu_motion_submit_stop_frame(source);
}

esp_err_t mcu_motion_service_handle_link_event(const mcu_link_event_t *event)
{
    uint32_t ref_seq;

    if (event == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    switch (event->type) {
        case MCU_LINK_RX_EVENT_ACK:
            ref_seq = decode_u32_le(event->frame.payload);
            if (s_command_inflight && ref_seq == s_last_command_seq) {
#if !defined(WATCHER_STRESS_BUILD) && !defined(CONFIG_WATCHER_STRESS_BUILD)
                ESP_LOGI(TAG, "Motion ACK ref_seq=%lu status=%u", (unsigned long)ref_seq,
                         (unsigned)decode_u16_le(&event->frame.payload[4]));
#endif
            }
            return ESP_OK;
        case MCU_LINK_RX_EVENT_NACK:
            ref_seq = decode_u32_le(event->frame.payload);
            if (s_command_inflight && ref_seq == s_last_command_seq) {
                ESP_LOGW(TAG, "Motion NACK ref_seq=%lu reason=0x%04x", (unsigned long)ref_seq,
                         (unsigned)decode_u16_le(&event->frame.payload[6]));
                s_command_inflight = false;
            }
            return ESP_OK;
        case MCU_LINK_RX_EVENT_FAULT:
            ref_seq = decode_u32_le(event->frame.payload);
            if (event->frame.payload[4] == 0x01u && (!s_command_inflight || ref_seq == s_last_command_seq || ref_seq == 0u)) {
                ESP_LOGW(TAG, "Motion FAULT ref_seq=%lu fault_code=0x%04x detail=0x%04x", (unsigned long)ref_seq,
                         (unsigned)decode_u16_le(&event->frame.payload[5]),
                         (unsigned)decode_u16_le(&event->frame.payload[7]));
                s_command_inflight = false;
            }
            return ESP_OK;
        case MCU_LINK_RX_EVENT_MOTION_DONE:
            ref_seq = decode_u32_le(event->frame.payload);
            if (!s_command_inflight || ref_seq == s_last_command_seq) {
#if !defined(WATCHER_STRESS_BUILD) && !defined(CONFIG_WATCHER_STRESS_BUILD)
                ESP_LOGI(TAG,
                         "Motion DONE ref_seq=%lu result=%u final=(%d,%d) exec_ms=%u",
                         (unsigned long)ref_seq, (unsigned)event->frame.payload[4],
                         (int)decode_i16_le(&event->frame.payload[5]), (int)decode_i16_le(&event->frame.payload[7]),
                         (unsigned)decode_u16_le(&event->frame.payload[9]));
                ESP_LOGI(OBS_TAG,
                         "evt=motion_done ref_seq=%lu msg_class=%u msg_id=%u result=%u final_x=%d final_y=%d "
                         "exec_ms=%u",
                         (unsigned long)ref_seq, (unsigned)MCU_FRAME_CLASS_MOTION, (unsigned)MCU_MOTION_MSG_MOTION_DONE,
                         (unsigned)event->frame.payload[4], (int)decode_i16_le(&event->frame.payload[5]),
                         (int)decode_i16_le(&event->frame.payload[7]), (unsigned)decode_u16_le(&event->frame.payload[9]));
#endif
                s_command_inflight = false;
            }
            return ESP_OK;
        default:
            return ESP_ERR_NOT_FOUND;
    }
}
