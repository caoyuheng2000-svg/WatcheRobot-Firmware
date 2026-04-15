#include "mcu_link_bootstrap.h"

#include "esp_log.h"
#include "mcu_link_uart.h"
#include "sdkconfig.h"

static const char *TAG = "MCU_LINK_BOOT";

static mcu_link_t s_link;
static bool s_link_initialized;

static esp_err_t mcu_link_bootstrap_init_uart(void)
{
#ifdef CONFIG_WATCHER_MCU_LINK_UART_ENABLE
    const mcu_link_uart_config_t config = {
        .port = (uart_port_t)CONFIG_WATCHER_MCU_LINK_UART_PORT_NUM,
        .tx_io_num = CONFIG_WATCHER_MCU_LINK_UART_TX_GPIO,
        .rx_io_num = CONFIG_WATCHER_MCU_LINK_UART_RX_GPIO,
        .baud_rate = CONFIG_WATCHER_MCU_LINK_UART_BAUD_RATE,
        .rx_buffer_size = CONFIG_WATCHER_MCU_LINK_UART_RX_BUFFER,
        .tx_buffer_size = CONFIG_WATCHER_MCU_LINK_UART_TX_BUFFER,
    };

    return mcu_link_uart_init(&config);
#else
    return ESP_OK;
#endif
}

esp_err_t mcu_link_bootstrap_init(void)
{
    esp_err_t ret;

    if (s_link_initialized) {
        return ESP_OK;
    }

    ret = mcu_link_init(&s_link);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "MCU link bootstrap init failed: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = mcu_link_bootstrap_init_uart();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "MCU link UART bootstrap init failed: %s", esp_err_to_name(ret));
        return ret;
    }

    s_link_initialized = true;
    ESP_LOGI(TAG, "MCU link bootstrap initialized (uart_ready=%d link_ready=%d ready=%d)",
             mcu_link_uart_is_ready() ? 1 : 0, mcu_link_is_link_ready(&s_link) ? 1 : 0, mcu_link_is_ready(&s_link) ? 1 : 0);
    return ESP_OK;
}

mcu_link_t *mcu_link_bootstrap_get_link(void)
{
    return s_link_initialized ? &s_link : NULL;
}

bool mcu_link_bootstrap_is_link_ready(void)
{
    return s_link_initialized && mcu_link_is_link_ready(&s_link);
}

bool mcu_link_bootstrap_is_ready(void)
{
    return s_link_initialized && mcu_link_is_ready(&s_link);
}
