#include "mcu_link.h"

esp_err_t mcu_link_init(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    mcu_link_stats_init(&link->stats);
    return mcu_link_fsm_init(&link->fsm);
}

esp_err_t mcu_link_reset(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    return mcu_link_fsm_init(&link->fsm);
}

esp_err_t mcu_link_begin_handshake(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    return mcu_link_fsm_begin_handshake(&link->fsm);
}

esp_err_t mcu_link_on_hello_rsp(mcu_link_t *link, bool snapshot_supported)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    return mcu_link_fsm_on_hello_rsp(&link->fsm, snapshot_supported);
}

esp_err_t mcu_link_mark_baseline_synced(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    return mcu_link_fsm_mark_baseline_synced(&link->fsm);
}

esp_err_t mcu_link_mark_degraded(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    return mcu_link_fsm_mark_degraded(&link->fsm);
}

esp_err_t mcu_link_begin_recovery(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    return mcu_link_fsm_begin_recovery(&link->fsm);
}

mcu_link_state_t mcu_link_get_state(const mcu_link_t *link)
{
    if (link == NULL) {
        return MCU_LINK_STATE_DOWN;
    }

    return mcu_link_fsm_get_state(&link->fsm);
}

bool mcu_link_is_link_ready(const mcu_link_t *link)
{
    return link != NULL && mcu_link_fsm_is_link_ready(&link->fsm);
}

bool mcu_link_is_ready(const mcu_link_t *link)
{
    return link != NULL && mcu_link_fsm_is_ready(&link->fsm);
}

const mcu_link_stats_t *mcu_link_get_stats(const mcu_link_t *link)
{
    if (link == NULL) {
        return NULL;
    }

    return &link->stats;
}

esp_err_t mcu_link_copy_stats(const mcu_link_t *link, mcu_link_stats_t *out_stats)
{
    if (link == NULL || out_stats == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    mcu_link_stats_copy(out_stats, &link->stats);
    return ESP_OK;
}

esp_err_t mcu_link_record_ack_timeout(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    mcu_link_stats_record_ack_timeout(&link->stats);
    return ESP_OK;
}

esp_err_t mcu_link_record_crc_error(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    mcu_link_stats_record_crc_error(&link->stats);
    return ESP_OK;
}

esp_err_t mcu_link_record_reconnect(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    mcu_link_stats_record_reconnect(&link->stats);
    return ESP_OK;
}

esp_err_t mcu_link_record_dropped_state(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    mcu_link_stats_record_dropped_state(&link->stats);
    return ESP_OK;
}

esp_err_t mcu_link_record_motion_done_fault(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    mcu_link_stats_record_motion_done_fault(&link->stats);
    return ESP_OK;
}
