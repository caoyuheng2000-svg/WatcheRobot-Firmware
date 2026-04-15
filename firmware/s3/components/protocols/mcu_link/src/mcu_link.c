#include "mcu_link.h"
#include "mcu_link_uart.h"

#include <string.h>

static uint32_t decode_u32_le(const uint8_t *src)
{
    return ((uint32_t)src[0]) | ((uint32_t)src[1] << 8u) | ((uint32_t)src[2] << 16u) | ((uint32_t)src[3] << 24u);
}

static uint32_t mcu_link_alloc_tx_seq(mcu_link_t *link)
{
    uint32_t seq = link->next_tx_seq;

    if (seq == 0u) {
        seq = 1u;
    }

    link->next_tx_seq = seq + 1u;
    return seq;
}

static bool mcu_link_parse_hello_rsp_snapshot_supported(const mcu_frame_t *frame, uint8_t *out_default_profile)
{
    const uint8_t *payload;

    if (frame == NULL) {
        return false;
    }

    if (frame->header.payload_len < 9u) {
        if (out_default_profile != NULL) {
            *out_default_profile = 0u;
        }
        return false;
    }

    payload = frame->payload;

    if (out_default_profile != NULL) {
        *out_default_profile = payload[8];
    }

    return (payload[5] & (1u << 5)) != 0u;
}

static esp_err_t mcu_link_handle_frame(mcu_link_t *link, const mcu_frame_t *frame, mcu_link_event_t *out_event)
{
    if (link == NULL || frame == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (out_event != NULL) {
        memset(out_event, 0, sizeof(*out_event));
        out_event->frame = *frame;
    }

    link->fsm.last_transition_seq = frame->header.seq;

    switch ((mcu_frame_class_t)frame->header.msg_class) {
        case MCU_FRAME_CLASS_SYS:
            switch ((mcu_sys_msg_id_t)frame->header.msg_id) {
                case MCU_SYS_MSG_HELLO_RSP: {
                    bool snapshot_supported = false;
                    uint8_t default_stream_profile = 0u;
                    mcu_link_state_t previous_state = mcu_link_get_state(link);

                    if (frame->header.payload_len < 9u) {
                        return ESP_ERR_NOT_FOUND;
                    }

                    snapshot_supported = mcu_link_parse_hello_rsp_snapshot_supported(frame, &default_stream_profile);
                    if (default_stream_profile != 0x01u) {
                        (void)mcu_link_mark_degraded(link);
                        return ESP_ERR_NOT_SUPPORTED;
                    }

                    if (previous_state == MCU_LINK_STATE_RECOVERING || previous_state == MCU_LINK_STATE_DEGRADED) {
                        mcu_link_record_reconnect(link);
                    }

                    if (previous_state != MCU_LINK_STATE_READY) {
                        (void)mcu_link_on_hello_rsp(link, snapshot_supported);
                    }

                    if (out_event != NULL) {
                        out_event->type = MCU_LINK_RX_EVENT_HELLO_RSP;
                    }
                    return ESP_OK;
                }
                case MCU_SYS_MSG_SNAPSHOT_RSP:
                    if (out_event != NULL) {
                        out_event->type = MCU_LINK_RX_EVENT_SNAPSHOT_RSP;
                    }
                    return ESP_OK;
                case MCU_SYS_MSG_ACK:
                    if (frame->header.payload_len < 6u) {
                        return ESP_ERR_NOT_FOUND;
                    }
                    if (out_event != NULL) {
                        out_event->type = MCU_LINK_RX_EVENT_ACK;
                    }
                    return ESP_OK;
                case MCU_SYS_MSG_NACK:
                    if (frame->header.payload_len < 8u) {
                        return ESP_ERR_NOT_FOUND;
                    }
                    if (mcu_link_get_state(link) == MCU_LINK_STATE_HANDSHAKING ||
                        mcu_link_get_state(link) == MCU_LINK_STATE_RECOVERING) {
                        (void)mcu_link_mark_degraded(link);
                    }
                    if (out_event != NULL) {
                        out_event->type = MCU_LINK_RX_EVENT_NACK;
                    }
                    return ESP_OK;
                case MCU_SYS_MSG_FAULT: {
                    uint8_t fault_source = 0u;
                    uint32_t ref_seq = 0u;

                    if (frame->header.payload_len < 9u) {
                        return ESP_ERR_NOT_FOUND;
                    }

                    ref_seq = decode_u32_le(frame->payload);
                    fault_source = frame->payload[4];

                    if (fault_source == 0x01u || ref_seq != 0u) {
                        mcu_link_record_motion_done_fault(link);
                    }

                    if (fault_source == 0x06u) {
                        (void)mcu_link_mark_degraded(link);
                    }

                    if (out_event != NULL) {
                        out_event->type = MCU_LINK_RX_EVENT_FAULT;
                    }
                    return ESP_OK;
                }
                default:
                    break;
            }
            break;
        case MCU_FRAME_CLASS_MOTION:
            if ((mcu_motion_msg_id_t)frame->header.msg_id == MCU_MOTION_MSG_MOTION_DONE) {
                if (frame->header.payload_len < 11u) {
                    return ESP_ERR_NOT_FOUND;
                }
                if (out_event != NULL) {
                    out_event->type = MCU_LINK_RX_EVENT_MOTION_DONE;
                }
                return ESP_OK;
            }
            break;
        case MCU_FRAME_CLASS_LED:
            if ((mcu_led_msg_id_t)frame->header.msg_id == MCU_LED_MSG_DONE) {
                if (frame->header.payload_len < 5u) {
                    return ESP_ERR_NOT_FOUND;
                }
                if (out_event != NULL) {
                    out_event->type = MCU_LINK_RX_EVENT_LED_DONE;
                }
                return ESP_OK;
            }
            break;
        case MCU_FRAME_CLASS_SENSOR:
            switch ((mcu_sensor_msg_id_t)frame->header.msg_id) {
                case MCU_SENSOR_MSG_TOUCH_EVENT:
                    if (frame->header.payload_len < 6u) {
                        return ESP_ERR_NOT_FOUND;
                    }
                    if (out_event != NULL) {
                        out_event->type = MCU_LINK_RX_EVENT_TOUCH_EVENT;
                    }
                    return ESP_OK;
                case MCU_SENSOR_MSG_MAG_STATE:
                    if (frame->header.payload_len < 6u) {
                        return ESP_ERR_NOT_FOUND;
                    }
                    if (out_event != NULL) {
                        out_event->type = MCU_LINK_RX_EVENT_MAG_STATE;
                    }
                    return ESP_OK;
                case MCU_SENSOR_MSG_IMU_STATE:
                    if (frame->header.payload_len < 11u) {
                        return ESP_ERR_NOT_FOUND;
                    }
                    if (out_event != NULL) {
                        out_event->type = MCU_LINK_RX_EVENT_IMU_STATE;
                    }
                    return ESP_OK;
                default:
                    break;
            }
            break;
        default:
            break;
    }

    return ESP_ERR_NOT_FOUND;
}

esp_err_t mcu_link_init(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    mcu_link_stats_init(&link->stats);
    link->next_tx_seq = 1u;
    link->rx.stream_len = 0u;
    return mcu_link_fsm_init(&link->fsm);
}

esp_err_t mcu_link_reset(mcu_link_t *link)
{
    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    link->next_tx_seq = 1u;
    link->rx.stream_len = 0u;
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

bool mcu_link_snapshot_supported(const mcu_link_t *link)
{
    return link != NULL && link->fsm.snapshot_supported;
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

esp_err_t mcu_link_poll(mcu_link_t *link, mcu_link_event_t *out_event)
{
    uint8_t read_buf[64];
    size_t buffered = 0u;
    size_t read_len = 0u;
    esp_err_t ret;

    if (link == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (out_event != NULL) {
        memset(out_event, 0, sizeof(*out_event));
    }

    if (!mcu_link_uart_is_ready()) {
        return ESP_ERR_INVALID_STATE;
    }

    ret = mcu_link_uart_get_buffered_bytes(&buffered);
    if (ret != ESP_OK) {
        return ret;
    }

    while (buffered > 0u) {
        const size_t chunk_len = (buffered < sizeof(read_buf)) ? buffered : sizeof(read_buf);
        size_t i;

        read_len = 0u;
        ret = mcu_link_uart_read(read_buf, chunk_len, 0u, &read_len);
        if (ret != ESP_OK) {
            return ret;
        }

        if (read_len == 0u) {
            break;
        }

        for (i = 0u; i < read_len; ++i) {
            const uint8_t byte = read_buf[i];

            if (byte == 0u) {
                if (link->rx.stream_len > 0u) {
                    uint8_t raw[MCU_FRAME_MAX_RAW_SIZE];
                    mcu_frame_t frame;
                    size_t raw_len = 0u;
                    size_t payload_len = 0u;
                    esp_err_t decode_ret;

                    decode_ret = mcu_wire_decode_raw(link->rx.stream, link->rx.stream_len, raw, sizeof(raw), &raw_len);
                    if (decode_ret != ESP_OK) {
                        mcu_link_record_crc_error(link);
                    } else {
                        decode_ret = mcu_frame_unpack(raw, raw_len, &frame, &payload_len);
                        if (decode_ret != ESP_OK) {
                            mcu_link_record_crc_error(link);
                        } else {
                            frame.header.payload_len = (uint16_t)payload_len;
                            decode_ret = mcu_link_handle_frame(link, &frame, out_event);
                            if (decode_ret == ESP_OK) {
                                link->rx.stream_len = 0u;
                                return ESP_OK;
                            }
                        }
                    }
                }

                link->rx.stream_len = 0u;
                continue;
            }

            if (link->rx.stream_len >= sizeof(link->rx.stream)) {
                mcu_link_record_crc_error(link);
                link->rx.stream_len = 0u;
            }

            link->rx.stream[link->rx.stream_len++] = byte;
        }

        ret = mcu_link_uart_get_buffered_bytes(&buffered);
        if (ret != ESP_OK) {
            return ret;
        }
    }

    return ESP_ERR_NOT_FOUND;
}
