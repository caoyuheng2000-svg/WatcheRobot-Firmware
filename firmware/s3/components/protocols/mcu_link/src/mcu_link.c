#include "mcu_link.h"

esp_err_t mcu_link_init(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    return mcu_link_fsm_init(&link->fsm);
}

esp_err_t mcu_link_reset(mcu_link_t *link)
{
    return mcu_link_init(link);
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
