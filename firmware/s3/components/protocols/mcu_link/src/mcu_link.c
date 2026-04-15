#include "mcu_link.h"
#include "mcu_link_uart.h"

static uint32_t mcu_link_alloc_tx_seq(mcu_link_t *link)
{
    uint32_t seq = link->next_tx_seq;

    if (seq == 0u) {
        seq = 1u;
    }

    link->next_tx_seq = seq + 1u;
    return seq;
}

esp_err_t mcu_link_init(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    mcu_link_stats_init(&link->stats);
    link->next_tx_seq = 1u;
    return mcu_link_fsm_init(&link->fsm);
}

esp_err_t mcu_link_reset(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    link->next_tx_seq = 1u;
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

esp_err_t mcu_link_send_frame(mcu_link_t *link,
                              uint8_t msg_class,
                              uint8_t msg_id,
                              uint8_t flags,
                              const uint8_t *payload,
                              uint16_t payload_len,
                              uint32_t *out_seq,
                              size_t *out_wire_len)
{
    mcu_frame_header_t header;
    uint8_t wire[MCU_FRAME_MAX_WIRE_SIZE];
    size_t wire_len = 0u;
    size_t written = 0u;
    uint32_t seq;
    esp_err_t ret;

    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (payload_len > MCU_FRAME_MAX_PAYLOAD_SIZE) {
        return ESP_ERR_INVALID_SIZE;
    }

    if (!mcu_link_uart_is_ready()) {
        return ESP_ERR_INVALID_STATE;
    }

    seq = mcu_link_alloc_tx_seq(link);
    mcu_frame_header_init(&header, msg_class, msg_id, flags, seq, payload_len);

    ret = mcu_wire_encode_frame(&header, payload, wire, sizeof(wire), &wire_len);
    if (ret != ESP_OK) {
        return ret;
    }

    ret = mcu_link_uart_write(wire, wire_len, &written);
    if (ret != ESP_OK) {
        return ret;
    }

    if (written != wire_len) {
        return ESP_ERR_INVALID_SIZE;
    }

    if (out_seq != NULL) {
        *out_seq = seq;
    }

    if (out_wire_len != NULL) {
        *out_wire_len = wire_len;
    }

    return ESP_OK;
}

esp_err_t mcu_link_send_hello_req(mcu_link_t *link, uint32_t *out_seq, size_t *out_wire_len)
{
    esp_err_t ret;

    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    ret = mcu_link_begin_handshake(link);
    if (ret != ESP_OK) {
        return ret;
    }

    return mcu_link_send_frame(link, MCU_FRAME_CLASS_SYS, MCU_SYS_MSG_HELLO_REQ, MCU_FRAME_FLAG_ACK_REQ, NULL, 0u,
                               out_seq, out_wire_len);
}
