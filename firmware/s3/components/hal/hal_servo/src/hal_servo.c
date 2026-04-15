/**
 * @file hal_servo.c
 * @brief Servo HAL: LEDC PWM direct drive on GPIO 19 (X) and GPIO 20 (Y)
 *
 * Phase 2 implementation: LEDC timer + smooth-move FreeRTOS task.
 *
 * GPIO mapping (from CLAUDE.md):
 *   GPIO 19 → Servo X axis (LEDC channel 0)
 *   GPIO 20 → Servo Y axis (LEDC channel 1)
 *
 * PWM Configuration:
 *   - 50Hz frequency (20ms period)
 *   - 14-bit resolution (16384 levels)
 *   - MS90 pulse width: 500us (logical 0 deg) to 2500us (logical 180 deg)
 *   - Logical neutral 90 deg -> physical neutral 1500us
 */

#include "hal_servo.h"
#include "driver/ledc.h"
#include "esp_log.h"
#include "mcu_motion_service.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include <ctype.h>
#include <stdint.h>
#include <string.h>

#define TAG "HAL_SERVO"

/* LEDC Configuration */
#define LEDC_TIMER_NUM LEDC_TIMER_0
#define LEDC_SPEED_MODE LEDC_LOW_SPEED_MODE
#define LEDC_DUTY_RES LEDC_TIMER_14_BIT
#define LEDC_FREQ_HZ 50
#define LEDC_CHANNEL_X LEDC_CHANNEL_0
#define LEDC_CHANNEL_Y LEDC_CHANNEL_1

/* MS90 servo PWM timing */
#define SERVO_PERIOD_US 20000
#define SERVO_MIN_PULSE_US 500
#define SERVO_NEUTRAL_PULSE_US 1500
#define SERVO_MAX_PULSE_US 2500
#define SERVO_LOGICAL_RANGE_DEG 180
#define SERVO_LOGICAL_NEUTRAL_DEG 90
#define SERVO_TRAVEL_FROM_NEUTRAL_US (SERVO_MAX_PULSE_US - SERVO_NEUTRAL_PULSE_US)
#define DUTY_RESOLUTION 16384

/* Smooth move task configuration */
#define SERVO_TASK_STACK_SIZE 4096
#define SERVO_TASK_PRIORITY 6
#define SERVO_CMD_QUEUE_SIZE 100

/* Default startup angles */
#define SERVO_X_DEFAULT_DEG 90
#define SERVO_Y_DEFAULT_DEG 120

/* Optional compatibility bridge to the MCU motion service */
#define SERVO_MOTION_BRIDGE_ENABLED CONFIG_WATCHER_SERVO_USE_MCU_MOTION_BRIDGE

/** Synchronized dual-axis move command */
typedef struct {
    int x_deg;
    int y_deg;
    int duration_ms;
} servo_sync_cmd_t;

/** Single-axis move command */
typedef struct {
    servo_axis_t axis;
    int angle_deg;
    int duration_ms;
} servo_move_cmd_t;

/** Combined command type for queue */
typedef enum { CMD_TYPE_SINGLE, CMD_TYPE_SYNC } cmd_type_t;

typedef struct {
    bool enabled;
    bool ready;
} servo_motion_bridge_state_t;

typedef struct {
    cmd_type_t type;
    uint32_t seq_no;
    uint32_t enqueued_ms;
    union {
        servo_move_cmd_t single;
        servo_sync_cmd_t sync;
    };
} servo_cmd_msg_t;

/* State variables */
static int s_angle[2] = {SERVO_X_DEFAULT_DEG, SERVO_Y_DEFAULT_DEG};
static bool s_initialized = false;
static QueueHandle_t s_cmd_queue = NULL;
static TaskHandle_t s_servo_task = NULL;
static SemaphoreHandle_t s_angle_mutex = NULL;
static portMUX_TYPE s_cmd_seq_lock = portMUX_INITIALIZER_UNLOCKED;
static uint32_t s_cmd_seq = 0;
static portMUX_TYPE s_motion_cancel_lock = portMUX_INITIALIZER_UNLOCKED;
static uint32_t s_motion_cancel_generation = 0;
static servo_motion_bridge_state_t s_motion_bridge = {.enabled = SERVO_MOTION_BRIDGE_ENABLED, .ready = false};

/* Forward declarations */
static void servo_task(void *arg);
static int div_round_nearest(int numerator, int denominator);
static int servo_apply_rotation_direction(servo_axis_t axis, int relative_deg);
static int logical_angle_to_pulse_width_us(servo_axis_t axis, int logical_angle_deg);
static int pulse_width_us_to_duty(int pulse_width_us);
static int angle_to_duty_mapped(servo_axis_t axis, int logical_angle_deg);
static void servo_log_target_mapping(servo_axis_t axis, int logical_angle_deg, const char *context);
static esp_err_t set_duty(servo_axis_t axis, int duty);
static esp_err_t configure_ledc(void);
static void move_to_angle_immediate(servo_axis_t axis, int angle_deg);
static uint32_t servo_now_ms(void);
static uint32_t servo_next_seq(void);
static UBaseType_t servo_queue_depth(void);
static void servo_log_enqueue(const servo_cmd_msg_t *cmd);
static void servo_log_drop(const servo_cmd_msg_t *cmd, const char *reason);
static void servo_log_execute_start(const servo_cmd_msg_t *cmd);
static void servo_log_execute_done(const servo_cmd_msg_t *cmd, uint32_t exec_ms);
static uint32_t servo_cancel_generation(void);
static bool servo_cancel_requested(uint32_t generation);
static bool servo_bridge_is_ready(void);
static void servo_bridge_init(void);
static void servo_bridge_submit_single(servo_axis_t axis, int angle_deg, int duration_ms);
static void servo_bridge_submit_sync(int x_deg, int y_deg, int duration_ms);
static void servo_bridge_cancel_all(void);
static esp_err_t servo_build_motion_request(uint8_t axis_mask, int x_deg, int y_deg, int duration_ms,
                                            mcu_motion_request_t *out_request);

/**
 * @brief Divide and round to the nearest integer.
 *
 * Keeps the integer-only mapping stable for both positive and negative values.
 */
static int div_round_nearest(int numerator, int denominator) {
    if (numerator >= 0) {
        return (numerator + (denominator / 2)) / denominator;
    }

    return (numerator - (denominator / 2)) / denominator;
}

/**
 * @brief Apply the installation-specific rotation direction.
 *
 * The MS90 datasheet defines increasing pulse width as counterclockwise.
 * The current mechanical installation uses the same positive direction for
 * both logical axes, so this hook returns the relative angle unchanged.
 */
static int servo_apply_rotation_direction(servo_axis_t axis, int relative_deg) {
    (void)axis;
    return relative_deg;
}

/**
 * @brief Convert logical installation-space angle to MS90 pulse width.
 *
 * Public APIs continue to use logical angles in the 0-180 range where 90 deg
 * is the installed neutral position. Internally the MS90 is driven with a
 * 500-2500us pulse range and a 1500us neutral pulse.
 */
static int logical_angle_to_pulse_width_us(servo_axis_t axis, int logical_angle_deg) {
    int clamped_angle = logical_angle_deg;
    int logical_relative_deg;
    int physical_relative_deg;
    int pulse_width_us;

    if (clamped_angle < 0) {
        clamped_angle = 0;
    }
    if (clamped_angle > SERVO_LOGICAL_RANGE_DEG) {
        clamped_angle = SERVO_LOGICAL_RANGE_DEG;
    }

    logical_relative_deg = clamped_angle - SERVO_LOGICAL_NEUTRAL_DEG;
    physical_relative_deg = servo_apply_rotation_direction(axis, logical_relative_deg);

    if (physical_relative_deg < -SERVO_LOGICAL_NEUTRAL_DEG) {
        physical_relative_deg = -SERVO_LOGICAL_NEUTRAL_DEG;
    }
    if (physical_relative_deg > SERVO_LOGICAL_NEUTRAL_DEG) {
        physical_relative_deg = SERVO_LOGICAL_NEUTRAL_DEG;
    }

    pulse_width_us = SERVO_NEUTRAL_PULSE_US +
                     div_round_nearest(physical_relative_deg * SERVO_TRAVEL_FROM_NEUTRAL_US, SERVO_LOGICAL_NEUTRAL_DEG);

    if (pulse_width_us < SERVO_MIN_PULSE_US) {
        pulse_width_us = SERVO_MIN_PULSE_US;
    }
    if (pulse_width_us > SERVO_MAX_PULSE_US) {
        pulse_width_us = SERVO_MAX_PULSE_US;
    }

    return pulse_width_us;
}

/**
 * @brief Convert pulse width in microseconds to LEDC duty cycle value.
 */
static int pulse_width_us_to_duty(int pulse_width_us) {
    if (pulse_width_us < SERVO_MIN_PULSE_US) {
        pulse_width_us = SERVO_MIN_PULSE_US;
    }
    if (pulse_width_us > SERVO_MAX_PULSE_US) {
        pulse_width_us = SERVO_MAX_PULSE_US;
    }

    return div_round_nearest(pulse_width_us * DUTY_RESOLUTION, SERVO_PERIOD_US);
}

static int angle_to_duty_mapped(servo_axis_t axis, int logical_angle_deg) {
    return pulse_width_us_to_duty(logical_angle_to_pulse_width_us(axis, logical_angle_deg));
}

static void servo_log_target_mapping(servo_axis_t axis, int logical_angle_deg, const char *context) {
    int pulse_width_us = logical_angle_to_pulse_width_us(axis, logical_angle_deg);
    int duty = pulse_width_us_to_duty(pulse_width_us);

    ESP_LOGI(TAG, "Map servo %s axis=%s logical=%d pulse=%dus duty=%d", context != NULL ? context : "target",
             axis == SERVO_AXIS_X ? "X" : "Y", logical_angle_deg, pulse_width_us, duty);
}

/**
 * @brief Set LEDC duty cycle for a servo channel.
 *
 * @param axis Servo axis (X or Y)
 * @param duty Duty cycle value
 * @return ESP_OK on success
 */
static esp_err_t set_duty(servo_axis_t axis, int duty) {
    ledc_channel_t channel = (axis == SERVO_AXIS_X) ? LEDC_CHANNEL_X : LEDC_CHANNEL_Y;

    esp_err_t ret = ledc_set_duty(LEDC_SPEED_MODE, channel, duty);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to set duty for axis %d: %s", axis, esp_err_to_name(ret));
        return ret;
    }

    ret = ledc_update_duty(LEDC_SPEED_MODE, channel);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to update duty for axis %d: %s", axis, esp_err_to_name(ret));
        return ret;
    }

    return ESP_OK;
}

/**
 * @brief Configure LEDC timer and channels.
 *
 * @return ESP_OK on success, ESP_FAIL on configuration error
 */
static esp_err_t configure_ledc(void) {
    /* Timer configuration */
    ledc_timer_config_t timer_cfg = {.speed_mode = LEDC_SPEED_MODE,
                                     .duty_resolution = LEDC_DUTY_RES,
                                     .timer_num = LEDC_TIMER_NUM,
                                     .freq_hz = LEDC_FREQ_HZ,
                                     .clk_cfg = LEDC_AUTO_CLK};

    esp_err_t ret = ledc_timer_config(&timer_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "LEDC timer config failed: %s", esp_err_to_name(ret));
        return ESP_FAIL;
    }

    /* X-axis channel (GPIO 19) */
    ledc_channel_config_t ch_x = {.gpio_num = CONFIG_WATCHER_SERVO_X_GPIO,
                                  .speed_mode = LEDC_SPEED_MODE,
                                  .channel = LEDC_CHANNEL_X,
                                  .timer_sel = LEDC_TIMER_NUM,
                                  .duty = angle_to_duty_mapped(SERVO_AXIS_X, s_angle[SERVO_AXIS_X]),
                                  .hpoint = 0};

    ret = ledc_channel_config(&ch_x);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "LEDC channel X config failed: %s", esp_err_to_name(ret));
        return ESP_FAIL;
    }

    /* Y-axis channel (GPIO 20) */
    ledc_channel_config_t ch_y = {.gpio_num = CONFIG_WATCHER_SERVO_Y_GPIO,
                                  .speed_mode = LEDC_SPEED_MODE,
                                  .channel = LEDC_CHANNEL_Y,
                                  .timer_sel = LEDC_TIMER_NUM,
                                  .duty = angle_to_duty_mapped(SERVO_AXIS_Y, s_angle[SERVO_AXIS_Y]),
                                  .hpoint = 0};

    ret = ledc_channel_config(&ch_y);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "LEDC channel Y config failed: %s", esp_err_to_name(ret));
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "LEDC configured: %dHz, %d-bit, GPIO %d (X), GPIO %d (Y), pulse=%d..%dus neutral=%dus", LEDC_FREQ_HZ,
             LEDC_DUTY_RES, CONFIG_WATCHER_SERVO_X_GPIO, CONFIG_WATCHER_SERVO_Y_GPIO, SERVO_MIN_PULSE_US,
             SERVO_MAX_PULSE_US, SERVO_NEUTRAL_PULSE_US);

    return ESP_OK;
}

/**
 * @brief Move servo to angle immediately (no smoothing).
 *
 * @param axis Servo axis
 * @param angle_deg Target angle
 */
static void move_to_angle_immediate(servo_axis_t axis, int angle_deg) {
    int duty = angle_to_duty_mapped(axis, angle_deg);
    set_duty(axis, duty);

    if (xSemaphoreTake(s_angle_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
        s_angle[axis] = angle_deg;
        xSemaphoreGive(s_angle_mutex);
    }
}

static uint32_t servo_now_ms(void) {
    return (uint32_t)(xTaskGetTickCount() * portTICK_PERIOD_MS);
}

static uint32_t servo_next_seq(void) {
    uint32_t seq_no;

    portENTER_CRITICAL(&s_cmd_seq_lock);
    s_cmd_seq++;
    seq_no = s_cmd_seq;
    portEXIT_CRITICAL(&s_cmd_seq_lock);

    return seq_no;
}

static UBaseType_t servo_queue_depth(void) {
    return s_cmd_queue != NULL ? uxQueueMessagesWaiting(s_cmd_queue) : 0;
}

static void servo_log_enqueue(const servo_cmd_msg_t *cmd) {
    if (cmd == NULL) {
        return;
    }

    if (cmd->type == CMD_TYPE_SINGLE) {
        ESP_LOGI(TAG, "Queue servo cmd seq=%lu type=single axis=%s target=%d duration_ms=%d q_depth=%lu",
                 (unsigned long)cmd->seq_no, cmd->single.axis == SERVO_AXIS_X ? "X" : "Y", cmd->single.angle_deg,
                 cmd->single.duration_ms, (unsigned long)servo_queue_depth());
    } else {
        ESP_LOGI(TAG, "Queue servo cmd seq=%lu type=sync x=%d y=%d duration_ms=%d q_depth=%lu",
                 (unsigned long)cmd->seq_no, cmd->sync.x_deg, cmd->sync.y_deg, cmd->sync.duration_ms,
                 (unsigned long)servo_queue_depth());
    }
}

static void servo_log_drop(const servo_cmd_msg_t *cmd, const char *reason) {
    if (cmd == NULL) {
        return;
    }

    if (cmd->type == CMD_TYPE_SINGLE) {
        ESP_LOGW(TAG, "Drop servo cmd seq=%lu reason=%s axis=%s target=%d duration_ms=%d q_depth=%lu",
                 (unsigned long)cmd->seq_no, reason != NULL ? reason : "unknown",
                 cmd->single.axis == SERVO_AXIS_X ? "X" : "Y", cmd->single.angle_deg, cmd->single.duration_ms,
                 (unsigned long)servo_queue_depth());
    } else {
        ESP_LOGW(TAG, "Drop servo cmd seq=%lu reason=%s x=%d y=%d duration_ms=%d q_depth=%lu",
                 (unsigned long)cmd->seq_no, reason != NULL ? reason : "unknown", cmd->sync.x_deg, cmd->sync.y_deg,
                 cmd->sync.duration_ms, (unsigned long)servo_queue_depth());
    }
}

static void servo_log_execute_start(const servo_cmd_msg_t *cmd) {
    uint32_t waited_ms;

    if (cmd == NULL) {
        return;
    }

    waited_ms = servo_now_ms() - cmd->enqueued_ms;
    if (cmd->type == CMD_TYPE_SINGLE) {
        ESP_LOGI(TAG,
                 "Start servo cmd seq=%lu type=single axis=%s target=%d duration_ms=%d queued_ms=%lu q_remaining=%lu",
                 (unsigned long)cmd->seq_no, cmd->single.axis == SERVO_AXIS_X ? "X" : "Y", cmd->single.angle_deg,
                 cmd->single.duration_ms, (unsigned long)waited_ms, (unsigned long)servo_queue_depth());
        servo_log_target_mapping(cmd->single.axis, cmd->single.angle_deg, "cmd");
    } else {
        ESP_LOGI(TAG, "Start servo cmd seq=%lu type=sync x=%d y=%d duration_ms=%d queued_ms=%lu q_remaining=%lu",
                 (unsigned long)cmd->seq_no, cmd->sync.x_deg, cmd->sync.y_deg, cmd->sync.duration_ms,
                 (unsigned long)waited_ms, (unsigned long)servo_queue_depth());
        servo_log_target_mapping(SERVO_AXIS_X, cmd->sync.x_deg, "sync-x");
        servo_log_target_mapping(SERVO_AXIS_Y, cmd->sync.y_deg, "sync-y");
    }
}

static void servo_log_execute_done(const servo_cmd_msg_t *cmd, uint32_t exec_ms) {
    int current_x = hal_servo_get_angle(SERVO_AXIS_X);
    int current_y = hal_servo_get_angle(SERVO_AXIS_Y);

    if (cmd == NULL) {
        return;
    }

    ESP_LOGI(TAG, "Done servo cmd seq=%lu type=%s exec_ms=%lu final={x=%d y=%d} q_depth=%lu",
             (unsigned long)cmd->seq_no, cmd->type == CMD_TYPE_SINGLE ? "single" : "sync", (unsigned long)exec_ms,
             current_x, current_y, (unsigned long)servo_queue_depth());
}

static uint32_t servo_cancel_generation(void) {
    uint32_t generation;

    portENTER_CRITICAL(&s_motion_cancel_lock);
    generation = s_motion_cancel_generation;
    portEXIT_CRITICAL(&s_motion_cancel_lock);

    return generation;
}

static bool servo_cancel_requested(uint32_t generation) {
    return servo_cancel_generation() != generation;
}

static bool servo_bridge_is_ready(void) {
    return s_motion_bridge.enabled && s_motion_bridge.ready;
}

static esp_err_t servo_build_motion_request(uint8_t axis_mask, int x_deg, int y_deg, int duration_ms,
                                            mcu_motion_request_t *out_request) {
    if (out_request == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (axis_mask == 0U || (axis_mask & ~(MCU_MOTION_AXIS_X | MCU_MOTION_AXIS_Y)) != 0U) {
        return ESP_ERR_INVALID_ARG;
    }

    if (x_deg < 0 || x_deg > 180 || y_deg < 0 || y_deg > 180) {
        return ESP_ERR_INVALID_ARG;
    }

    if (duration_ms <= 0) {
        return ESP_ERR_INVALID_ARG;
    }

    out_request->axis_mask = axis_mask;
    out_request->x_deg_x10 = (axis_mask & MCU_MOTION_AXIS_X) != 0U ? (int16_t)(x_deg * 10) : 0;
    out_request->y_deg_x10 = (axis_mask & MCU_MOTION_AXIS_Y) != 0U ? (int16_t)(y_deg * 10) : 0;
    out_request->duration_ms = duration_ms > UINT16_MAX ? UINT16_MAX : (uint16_t)duration_ms;
    out_request->motion_profile = MCU_MOTION_PROFILE_LINEAR;
    out_request->source = MCU_MOTION_SOURCE_UNKNOWN;

    return ESP_OK;
}

static void servo_bridge_submit_single(servo_axis_t axis, int angle_deg, int duration_ms) {
    if (!servo_bridge_is_ready()) {
        return;
    }

    mcu_motion_request_t request;
    esp_err_t ret = servo_build_motion_request(axis == SERVO_AXIS_X ? MCU_MOTION_AXIS_X : MCU_MOTION_AXIS_Y,
                                               axis == SERVO_AXIS_X ? angle_deg : 0, axis == SERVO_AXIS_Y ? angle_deg : 0,
                                               duration_ms, &request);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Bridge motion request rejected: axis=%s angle=%d duration_ms=%d error=%s",
                 axis == SERVO_AXIS_X ? "X" : "Y", angle_deg, duration_ms, esp_err_to_name(ret));
        return;
    }

    ret = mcu_motion_submit(&request);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Bridge smooth motion submit failed: axis=%s angle=%d duration_ms=%d error=%s",
                 axis == SERVO_AXIS_X ? "X" : "Y", angle_deg, duration_ms, esp_err_to_name(ret));
        return;
    }

    ESP_LOGI(TAG, "Mirrored smooth motion to MCU service: axis=%s angle=%d duration_ms=%d",
             axis == SERVO_AXIS_X ? "X" : "Y", angle_deg, duration_ms);
}

static void servo_bridge_submit_sync(int x_deg, int y_deg, int duration_ms) {
    if (!servo_bridge_is_ready()) {
        return;
    }

    mcu_motion_request_t request;
    esp_err_t ret = servo_build_motion_request(MCU_MOTION_AXIS_X | MCU_MOTION_AXIS_Y, x_deg, y_deg, duration_ms,
                                               &request);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Bridge sync motion request rejected: x=%d y=%d duration_ms=%d error=%s", x_deg, y_deg,
                 duration_ms, esp_err_to_name(ret));
        return;
    }

    ret = mcu_motion_submit(&request);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Bridge sync motion submit failed: x=%d y=%d duration_ms=%d error=%s", x_deg, y_deg,
                 duration_ms, esp_err_to_name(ret));
        return;
    }

    ESP_LOGI(TAG, "Mirrored sync motion to MCU service: x=%d y=%d duration_ms=%d", x_deg, y_deg, duration_ms);
}

static void servo_bridge_cancel_all(void) {
    if (!servo_bridge_is_ready()) {
        return;
    }

    esp_err_t ret = mcu_motion_stop(MCU_MOTION_SOURCE_UNKNOWN);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Bridge motion cancel failed: error=%s", esp_err_to_name(ret));
        return;
    }

    ESP_LOGI(TAG, "Mirrored motion cancel to MCU service");
}

static void servo_bridge_init(void) {
    if (!s_motion_bridge.enabled) {
        return;
    }

    esp_err_t ret = mcu_motion_service_init();
    if (ret != ESP_OK) {
        s_motion_bridge.ready = false;
        ESP_LOGW(TAG, "MCU motion bridge unavailable; staying on local servo path: %s", esp_err_to_name(ret));
        return;
    }

    s_motion_bridge.ready = true;
    ESP_LOGI(TAG, "MCU motion bridge enabled");
}

/**
 * @brief Background task for smooth servo movement.
 *
 * Processes commands from queue and performs linear interpolation.
 *
 * @param arg Unused
 */
static void servo_task(void *arg) {
    (void)arg;
    servo_cmd_msg_t cmd;
    const TickType_t step_interval = pdMS_TO_TICKS(CONFIG_WATCHER_SERVO_SMOOTH_STEP_MS);

    ESP_LOGI(TAG, "Servo task started (step interval: %dms)", CONFIG_WATCHER_SERVO_SMOOTH_STEP_MS);

    while (1) {
        if (xQueueReceive(s_cmd_queue, &cmd, pdMS_TO_TICKS(100)) != pdTRUE) {
            /* No command, continue waiting */
            continue;
        }

        servo_log_execute_start(&cmd);
        uint32_t exec_started_ms = servo_now_ms();
        uint32_t cancel_generation = servo_cancel_generation();

        if (cmd.type == CMD_TYPE_SINGLE) {
            /* Single-axis smooth move */
            servo_axis_t axis = cmd.single.axis;
            int target_deg = cmd.single.angle_deg;
            int duration_ms = cmd.single.duration_ms;
            TickType_t last_wake_tick = xTaskGetTickCount();

            /* Clamp Y-axis to mechanical limits */
            if (axis == SERVO_AXIS_Y) {
                if (target_deg < CONFIG_WATCHER_SERVO_Y_MIN_DEG) {
                    target_deg = CONFIG_WATCHER_SERVO_Y_MIN_DEG;
                }
                if (target_deg > CONFIG_WATCHER_SERVO_Y_MAX_DEG) {
                    target_deg = CONFIG_WATCHER_SERVO_Y_MAX_DEG;
                }
            }

            /* Get current angle */
            int start_deg;
            if (xSemaphoreTake(s_angle_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
                start_deg = s_angle[axis];
                xSemaphoreGive(s_angle_mutex);
            } else {
                continue;
            }

            /* Skip if already at target */
            if (start_deg == target_deg) {
                ESP_LOGI(TAG, "Skip servo cmd seq=%lu axis=%s already at target=%d", (unsigned long)cmd.seq_no,
                         axis == SERVO_AXIS_X ? "X" : "Y", target_deg);
                servo_log_execute_done(&cmd, servo_now_ms() - exec_started_ms);
                continue;
            }

            /* Calculate steps */
            int num_steps = duration_ms / CONFIG_WATCHER_SERVO_SMOOTH_STEP_MS;
            if (num_steps < 1)
                num_steps = 1;

            float step_size = (float)(target_deg - start_deg) / num_steps;

            ESP_LOGD(TAG, "Smooth move: axis=%s, start=%d, target=%d, steps=%d", axis == SERVO_AXIS_X ? "X" : "Y",
                     start_deg, target_deg, num_steps);

            /* Interpolate */
            for (int i = 1; i <= num_steps; i++) {
                int current_deg;

                if (servo_cancel_requested(cancel_generation)) {
                    ESP_LOGI(TAG, "Abort servo cmd seq=%lu type=single due_to=cancel", (unsigned long)cmd.seq_no);
                    break;
                }

                if (i == num_steps) {
                    current_deg = target_deg;
                } else {
                    current_deg = start_deg + (int)(step_size * i);
                }

                int duty = angle_to_duty_mapped(axis, current_deg);
                set_duty(axis, duty);

                /* Update stored angle */
                if (xSemaphoreTake(s_angle_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
                    s_angle[axis] = current_deg;
                    xSemaphoreGive(s_angle_mutex);
                }

                (void)xTaskDelayUntil(&last_wake_tick, step_interval);
            }

        } else if (cmd.type == CMD_TYPE_SYNC) {
            /* Synchronized dual-axis move */
            int target_x = cmd.sync.x_deg;
            int target_y = cmd.sync.y_deg;
            int duration_ms = cmd.sync.duration_ms;
            TickType_t last_wake_tick = xTaskGetTickCount();

            /* Clamp Y-axis to mechanical limits */
            if (target_y < CONFIG_WATCHER_SERVO_Y_MIN_DEG) {
                target_y = CONFIG_WATCHER_SERVO_Y_MIN_DEG;
            }
            if (target_y > CONFIG_WATCHER_SERVO_Y_MAX_DEG) {
                target_y = CONFIG_WATCHER_SERVO_Y_MAX_DEG;
            }

            /* Get current angles */
            int start_x, start_y;
            if (xSemaphoreTake(s_angle_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
                start_x = s_angle[SERVO_AXIS_X];
                start_y = s_angle[SERVO_AXIS_Y];
                xSemaphoreGive(s_angle_mutex);
            } else {
                continue;
            }

            /* Calculate steps */
            int num_steps = duration_ms / CONFIG_WATCHER_SERVO_SMOOTH_STEP_MS;
            if (num_steps < 1)
                num_steps = 1;

            float step_x = (float)(target_x - start_x) / num_steps;
            float step_y = (float)(target_y - start_y) / num_steps;

            ESP_LOGD(TAG, "Sync move: X %d->%d, Y %d->%d, steps=%d", start_x, target_x, start_y, target_y, num_steps);

            /* Interpolate both axes */
            for (int i = 1; i <= num_steps; i++) {
                int current_x, current_y;

                if (servo_cancel_requested(cancel_generation)) {
                    ESP_LOGI(TAG, "Abort servo cmd seq=%lu type=sync due_to=cancel", (unsigned long)cmd.seq_no);
                    break;
                }

                if (i == num_steps) {
                    current_x = target_x;
                    current_y = target_y;
                } else {
                    current_x = start_x + (int)(step_x * i);
                    current_y = start_y + (int)(step_y * i);
                }

                int duty_x = angle_to_duty_mapped(SERVO_AXIS_X, current_x);
                int duty_y = angle_to_duty_mapped(SERVO_AXIS_Y, current_y);

                set_duty(SERVO_AXIS_X, duty_x);
                set_duty(SERVO_AXIS_Y, duty_y);

                /* Update stored angles */
                if (xSemaphoreTake(s_angle_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
                    s_angle[SERVO_AXIS_X] = current_x;
                    s_angle[SERVO_AXIS_Y] = current_y;
                    xSemaphoreGive(s_angle_mutex);
                }

                (void)xTaskDelayUntil(&last_wake_tick, step_interval);
            }
        }

        servo_log_execute_done(&cmd, servo_now_ms() - exec_started_ms);
    }
}

esp_err_t hal_servo_init(void) {
    if (s_initialized) {
        return ESP_OK;
    }

    /* Create mutex for thread-safe angle access */
    s_angle_mutex = xSemaphoreCreateMutex();
    if (s_angle_mutex == NULL) {
        ESP_LOGE(TAG, "Failed to create angle mutex");
        return ESP_FAIL;
    }

    /* Configure LEDC */
    esp_err_t ret = configure_ledc();
    if (ret != ESP_OK) {
        vSemaphoreDelete(s_angle_mutex);
        s_angle_mutex = NULL;
        return ret;
    }

    /* Create command queue */
    s_cmd_queue = xQueueCreate(SERVO_CMD_QUEUE_SIZE, sizeof(servo_cmd_msg_t));
    if (s_cmd_queue == NULL) {
        ESP_LOGE(TAG, "Failed to create command queue");
        vSemaphoreDelete(s_angle_mutex);
        s_angle_mutex = NULL;
        return ESP_FAIL;
    }

    /* Create servo task */
    BaseType_t task_ret =
        xTaskCreate(servo_task, "servo_task", SERVO_TASK_STACK_SIZE, NULL, SERVO_TASK_PRIORITY, &s_servo_task);

    if (task_ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create servo task");
        vQueueDelete(s_cmd_queue);
        s_cmd_queue = NULL;
        vSemaphoreDelete(s_angle_mutex);
        s_angle_mutex = NULL;
        return ESP_FAIL;
    }

    s_initialized = true;
    servo_bridge_init();
    ESP_LOGI(TAG, "Servo HAL initialized: X=GPIO%d, Y=GPIO%d, startup=[%d,%d]deg, Y limits=[%d,%d]deg",
             CONFIG_WATCHER_SERVO_X_GPIO, CONFIG_WATCHER_SERVO_Y_GPIO, SERVO_X_DEFAULT_DEG, SERVO_Y_DEFAULT_DEG,
             CONFIG_WATCHER_SERVO_Y_MIN_DEG, CONFIG_WATCHER_SERVO_Y_MAX_DEG);

    return ESP_OK;
}

esp_err_t hal_servo_set_angle(servo_axis_t axis, int angle_deg) {
    if (!s_initialized) {
        ESP_LOGW(TAG, "Servo not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    if (axis != SERVO_AXIS_X && axis != SERVO_AXIS_Y) {
        return ESP_ERR_INVALID_ARG;
    }

    /* Validate angle range */
    if (angle_deg < 0 || angle_deg > 180) {
        return ESP_ERR_INVALID_ARG;
    }

    /* Clamp Y-axis to mechanical limits */
    if (axis == SERVO_AXIS_Y) {
        if (angle_deg < CONFIG_WATCHER_SERVO_Y_MIN_DEG) {
            angle_deg = CONFIG_WATCHER_SERVO_Y_MIN_DEG;
        }
        if (angle_deg > CONFIG_WATCHER_SERVO_Y_MAX_DEG) {
            angle_deg = CONFIG_WATCHER_SERVO_Y_MAX_DEG;
        }
    }

    move_to_angle_immediate(axis, angle_deg);
    ESP_LOGI(TAG, "Set angle: axis=%s, angle=%d", axis == SERVO_AXIS_X ? "X" : "Y", angle_deg);

    return ESP_OK;
}

esp_err_t hal_servo_move_smooth(servo_axis_t axis, int angle_deg, int duration_ms) {
    if (!s_initialized) {
        ESP_LOGW(TAG, "Servo not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    if (axis != SERVO_AXIS_X && axis != SERVO_AXIS_Y) {
        return ESP_ERR_INVALID_ARG;
    }

    /* Validate angle range */
    if (angle_deg < 0 || angle_deg > 180) {
        return ESP_ERR_INVALID_ARG;
    }

    /* For zero duration, use immediate move */
    if (duration_ms <= 0) {
        ESP_LOGI(TAG, "Immediate servo cmd type=single axis=%s target=%d duration_ms=%d",
                 axis == SERVO_AXIS_X ? "X" : "Y", angle_deg, duration_ms);
        return hal_servo_set_angle(axis, angle_deg);
    }

    servo_bridge_submit_single(axis, angle_deg, duration_ms);

    /* Enqueue smooth move command */
    servo_cmd_msg_t cmd = {.type = CMD_TYPE_SINGLE,
                           .seq_no = servo_next_seq(),
                           .enqueued_ms = servo_now_ms(),
                           .single = {.axis = axis, .angle_deg = angle_deg, .duration_ms = duration_ms}};

    /* Try to send, if queue full - drop oldest command and retry */
    if (xQueueSend(s_cmd_queue, &cmd, 0) != pdTRUE) {
        servo_cmd_msg_t dropped;
        if (xQueueReceive(s_cmd_queue, &dropped, 0) == pdTRUE) {
            servo_log_drop(&dropped, "queue_full_make_room");
        }
        if (xQueueSend(s_cmd_queue, &cmd, 0) != pdTRUE) {
            ESP_LOGW(TAG, "Command queue full even after drop");
            return ESP_ERR_TIMEOUT;
        }
    }

    servo_log_enqueue(&cmd);

    return ESP_OK;
}

esp_err_t hal_servo_move_sync(int x_deg, int y_deg, int duration_ms) {
    if (!s_initialized) {
        ESP_LOGW(TAG, "Servo not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    /* Validate angles */
    if (x_deg < 0 || x_deg > 180 || y_deg < 0 || y_deg > 180) {
        return ESP_ERR_INVALID_ARG;
    }

    /* For zero duration, use immediate moves */
    if (duration_ms <= 0) {
        ESP_LOGI(TAG, "Immediate servo cmd type=sync x=%d y=%d duration_ms=%d", x_deg, y_deg, duration_ms);
        esp_err_t ret_x = hal_servo_set_angle(SERVO_AXIS_X, x_deg);
        esp_err_t ret_y = hal_servo_set_angle(SERVO_AXIS_Y, y_deg);
        return (ret_x != ESP_OK) ? ret_x : ret_y;
    }

    servo_bridge_submit_sync(x_deg, y_deg, duration_ms);

    /* Enqueue synchronized move command */
    servo_cmd_msg_t cmd = {.type = CMD_TYPE_SYNC,
                           .seq_no = servo_next_seq(),
                           .enqueued_ms = servo_now_ms(),
                           .sync = {.x_deg = x_deg, .y_deg = y_deg, .duration_ms = duration_ms}};

    /* Try to send, if queue full - drop oldest command and retry */
    if (xQueueSend(s_cmd_queue, &cmd, 0) != pdTRUE) {
        servo_cmd_msg_t dropped;
        if (xQueueReceive(s_cmd_queue, &dropped, 0) == pdTRUE) {
            servo_log_drop(&dropped, "queue_full_make_room");
        }
        if (xQueueSend(s_cmd_queue, &cmd, 0) != pdTRUE) {
            ESP_LOGW(TAG, "Command queue full even after drop");
            return ESP_ERR_TIMEOUT;
        }
    }

    servo_log_enqueue(&cmd);

    return ESP_OK;
}

esp_err_t hal_servo_send_cmd(const char *id, int angle_deg, int duration_ms) {
    if (!id) {
        return ESP_ERR_INVALID_ARG;
    }

    servo_axis_t axis;
    char upper = (char)toupper((unsigned char)id[0]);

    if (upper == 'X') {
        axis = SERVO_AXIS_X;
    } else if (upper == 'Y') {
        axis = SERVO_AXIS_Y;
    } else {
        ESP_LOGW(TAG, "Unknown servo id: %s", id);
        return ESP_ERR_INVALID_ARG;
    }

    return hal_servo_move_smooth(axis, angle_deg, duration_ms);
}

esp_err_t hal_servo_cancel_all(void) {
    servo_cmd_msg_t dropped;

    if (!s_initialized || s_cmd_queue == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    servo_bridge_cancel_all();

    portENTER_CRITICAL(&s_motion_cancel_lock);
    s_motion_cancel_generation++;
    portEXIT_CRITICAL(&s_motion_cancel_lock);

    while (xQueueReceive(s_cmd_queue, &dropped, 0) == pdTRUE) {
        servo_log_drop(&dropped, "cancel_all");
    }

    ESP_LOGI(TAG, "Canceled servo motions; q_depth=%lu", (unsigned long)servo_queue_depth());
    return ESP_OK;
}

int hal_servo_get_angle(servo_axis_t axis) {
    if (!s_initialized) {
        return -1;
    }

    if (axis != SERVO_AXIS_X && axis != SERVO_AXIS_Y) {
        return -1;
    }

    int angle = -1;
    if (xSemaphoreTake(s_angle_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
        angle = s_angle[axis];
        xSemaphoreGive(s_angle_mutex);
    }

    return angle;
}
