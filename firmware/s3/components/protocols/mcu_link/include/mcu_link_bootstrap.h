/**
 * @file mcu_link_bootstrap.h
 * @brief App-facing bootstrap helpers for the static MCU link instance.
 */

#ifndef MCU_LINK_BOOTSTRAP_H
#define MCU_LINK_BOOTSTRAP_H

#include "mcu_link.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t mcu_link_bootstrap_init(void);
esp_err_t mcu_link_bootstrap_start(void);
mcu_link_t *mcu_link_bootstrap_get_link(void);
mcu_link_state_t mcu_link_bootstrap_get_state(void);
bool mcu_link_bootstrap_is_link_ready(void);
bool mcu_link_bootstrap_is_ready(void);

#ifdef __cplusplus
}
#endif

#endif /* MCU_LINK_BOOTSTRAP_H */
