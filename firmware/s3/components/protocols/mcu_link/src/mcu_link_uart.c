#include "mcu_link_uart.h"

#include "esp_check.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "MCU_LINK_UART";

typedef struct {
    bool ready;
    mcu_link_uart_config_t config;
} mcu_link_uart_state_t;

static mcu_link_uart_state_t s_uart;

esp_err_t mcu_link_uart_init(const mcu_link_uart_config_t *config)
{
    uart_config_t uart_config = {0};
    esp_err_t ret;

    ESP_RETURN_ON_FALSE(config != NULL, ESP_ERR_INVALID_ARG, TAG, "missing config");

    if (s_uart.ready) {
        if (memcmp(&s_uart.config, config, sizeof(*config)) == 0) {
            return ESP_OK;
        }
        mcu_link_uart_deinit();
    }

    uart_config.baud_rate = config->baud_rate;
    uart_config.data_bits = UART_DATA_8_BITS;
    uart_config.parity = UART_PARITY_DISABLE;
    uart_config.stop_bits = UART_STOP_BITS_1;
    uart_config.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    uart_config.source_clk = UART_SCLK_DEFAULT;

    ESP_RETURN_ON_ERROR(uart_param_config(config->port, &uart_config), TAG, "uart_param_config failed");
    ESP_RETURN_ON_ERROR(uart_set_pin(config->port, config->tx_io_num, config->rx_io_num, UART_PIN_NO_CHANGE,
                                     UART_PIN_NO_CHANGE),
                        TAG, "uart_set_pin failed");

    ret = uart_driver_install(config->port, config->rx_buffer_size, config->tx_buffer_size, 0, NULL, ESP_INTR_FLAG_SHARED);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "uart_driver_install failed: %s", esp_err_to_name(ret));
        return ret;
    }

    s_uart.ready = true;
    s_uart.config = *config;
    ESP_LOGI(TAG, "Runtime UART ready: uart=%d tx=%d rx=%d baud=%d rx_buf=%d tx_buf=%d", (int)config->port,
             config->tx_io_num, config->rx_io_num, config->baud_rate, config->rx_buffer_size,
             config->tx_buffer_size);
    return ESP_OK;
}

void mcu_link_uart_deinit(void)
{
    if (!s_uart.ready) {
        return;
    }

    (void)uart_driver_delete(s_uart.config.port);
    memset(&s_uart, 0, sizeof(s_uart));
}

bool mcu_link_uart_is_ready(void)
{
    return s_uart.ready;
}

uart_port_t mcu_link_uart_get_port(void)
{
    return s_uart.ready ? s_uart.config.port : UART_NUM_MAX;
}
