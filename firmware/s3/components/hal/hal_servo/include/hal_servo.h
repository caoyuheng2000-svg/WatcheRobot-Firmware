/**
 * @file hal_servo.h
 * @brief Servo HAL: LEDC PWM direct drive on GPIO 19 (X) and GPIO 20 (Y)
 *
 * Replaces the UART-to-MCU servo bridge used in v1.x.
 * GPIO 19/20 are repurposed from UART TX/RX to LEDC PWM channels.
 *
 * Features:
 *   - 50Hz, 14-bit LEDC PWM
 *   - Smooth movement with linear interpolation
 *   - Synchronized dual-axis motion
 *   - Y-axis mechanical limit protection
 */

#ifndef HAL_SERVO_H
#define HAL_SERVO_H

#include "esp_err.h"
#include <stdbool.h>

/** Servo axis selector */
typedef enum {
    SERVO_AXIS_X = 0, /*!< X axis (GPIO 19, left/right pan) */
    SERVO_AXIS_Y = 1, /*!< Y axis (GPIO 20, up/down tilt) */
} servo_axis_t;

/**
 * @brief Initialize servo HAL with LEDC PWM output.
 *
 * Configures GPIO 19 (X axis) and GPIO 20 (Y axis) as LEDC PWM channels
 * and starts the smooth-move background task.
 *
 * Logical angle model:
 *   - Public APIs use installation-space logical angles in the 0-180 range
 *   - 90° is the installed neutral position for the current mechanism
 *   - Internally the HAL maps logical 90° to the MS90 neutral pulse of 1500us
 *
 * Startup defaults applied directly by hal_servo_init():
 *   - X axis: 90°
 *   - Y axis: 90°
 *
 * Note: some behavior states later move Y to 120° after startup. That behavior
 * is defined by the state/action resources, not by the HAL defaults.
 *
 * @note Must be called before any hal_servo_set_angle() calls.
 * @note GPIO 19/20 are repurposed from UART (MCU communication removed in v2.0).
 *
 * @return
 *   - ESP_OK    on success
 *   - ESP_FAIL  if LEDC timer/channel configuration fails
 */
esp_err_t hal_servo_init(void);

/**
 * @brief Set servo angle immediately (no smoothing).
 *
 * @param axis    Servo axis (X or Y)
 * @param angle   Target logical angle in degrees (0–180, neutral at 90)
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if angle out of range
 */
esp_err_t hal_servo_set_angle(servo_axis_t axis, int angle_deg);

/**
 * @brief Move servo to angle with smooth interpolation.
 *
 * Enqueues a smooth move command. The background task interpolates
 * from current position to target over duration_ms milliseconds.
 *
 * @param axis        Servo axis (X or Y)
 * @param angle_deg   Target logical angle (0–180, neutral at 90)
 * @param duration_ms Movement duration in milliseconds
 * @return ESP_OK on success
 */
esp_err_t hal_servo_move_smooth(servo_axis_t axis, int angle_deg, int duration_ms);

/**
 * @brief Move both axes simultaneously.
 *
 * @param x_deg       Target logical X angle (0–180, neutral at 90)
 * @param y_deg       Target logical Y angle (0–180, neutral at 90)
 * @param duration_ms Movement duration in milliseconds
 * @return ESP_OK on success
 */
esp_err_t hal_servo_move_sync(int x_deg, int y_deg, int duration_ms);

/**
 * @brief Send servo command by axis name string (for WebSocket handler).
 *
 * Convenience wrapper for on_servo_handler: maps id string "X"/"Y" to
 * hal_servo_move_smooth() call.
 *
 * @param id          Axis identifier ("X" or "Y", case-insensitive)
 * @param angle_deg   Target logical angle (0–180, neutral at 90)
 * @param duration_ms Movement duration in milliseconds
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if id is unknown
 */
esp_err_t hal_servo_send_cmd(const char *id, int angle_deg, int duration_ms);

/**
 * @brief Get current servo angle.
 *
 * @param axis Servo axis
 * @return Current logical angle in degrees, or -1 if not initialized
 */
int hal_servo_get_angle(servo_axis_t axis);

#endif /* HAL_SERVO_H */
