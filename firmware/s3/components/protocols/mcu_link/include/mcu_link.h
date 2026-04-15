/**
 * @file mcu_link.h
 * @brief Public umbrella header for the coprocessor UART protocol core.
 */

#ifndef MCU_LINK_H
#define MCU_LINK_H

#include "mcu_cobs.h"
#include "mcu_crc16.h"
#include "mcu_frame.h"
#include "mcu_link_fsm.h"
#include "mcu_link_stats.h"
#include "mcu_wire.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    mcu_link_fsm_t fsm;
    mcu_link_stats_t stats;
} mcu_link_t;

esp_err_t mcu_link_init(mcu_link_t *link);
esp_err_t mcu_link_reset(mcu_link_t *link);
esp_err_t mcu_link_begin_handshake(mcu_link_t *link);
esp_err_t mcu_link_on_hello_rsp(mcu_link_t *link, bool snapshot_supported);
esp_err_t mcu_link_mark_baseline_synced(mcu_link_t *link);
esp_err_t mcu_link_mark_degraded(mcu_link_t *link);
esp_err_t mcu_link_begin_recovery(mcu_link_t *link);
mcu_link_state_t mcu_link_get_state(const mcu_link_t *link);
bool mcu_link_is_link_ready(const mcu_link_t *link);
bool mcu_link_is_ready(const mcu_link_t *link);
const mcu_link_stats_t *mcu_link_get_stats(const mcu_link_t *link);
esp_err_t mcu_link_copy_stats(const mcu_link_t *link, mcu_link_stats_t *out_stats);
esp_err_t mcu_link_record_ack_timeout(mcu_link_t *link);
esp_err_t mcu_link_record_crc_error(mcu_link_t *link);
esp_err_t mcu_link_record_reconnect(mcu_link_t *link);
esp_err_t mcu_link_record_dropped_state(mcu_link_t *link);
esp_err_t mcu_link_record_motion_done_fault(mcu_link_t *link);

#ifdef __cplusplus
}
#endif

#endif /* MCU_LINK_H */
