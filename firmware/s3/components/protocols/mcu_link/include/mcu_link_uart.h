/**
 * @file mcu_link_uart.h
 * @brief Minimal UART transport scaffold for the STM32 coprocessor link.
 */

#ifndef MCU_LINK_UART_H
#define MCU_LINK_UART_H

#include "driver/uart.h"
#include "esp_err.h"
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uart_port_t port;
    int tx_io_num;
    int rx_io_num;
    int baud_rate;
    int rx_buffer_size;
    int tx_buffer_size;
} mcu_link_uart_config_t;

esp_err_t mcu_link_uart_init(const mcu_link_uart_config_t *config);
void mcu_link_uart_deinit(void);
bool mcu_link_uart_is_ready(void);
uart_port_t mcu_link_uart_get_port(void);

#ifdef __cplusplus
}
#endif

#endif /* MCU_LINK_UART_H */
