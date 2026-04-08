/**
 * @file anim_player.c
 * @brief SD-backed animation player with ring-buffered stream playback.
 */

#include "anim_player.h"

#include "esp_log.h"
#include "esp_lvgl_port.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include <string.h>

#define TAG "ANIM_PLAYER"
#define ANIM_SOURCE_FRAME_SIZE 206
#define ANIM_SOURCE_FRAME_PIVOT (ANIM_SOURCE_FRAME_SIZE / 2)
#define ANIM_DISPLAY_ZOOM_2X (LV_IMG_ZOOM_NONE * 2)
#define ANIM_TIMER_TICK_MS 10U
#define ANIM_WORKER_IDLE_MS 5U

typedef enum {
    ANIM_PLAYER_IDLE = 0,
    ANIM_PLAYER_SWITCH_PREPARING,
    ANIM_PLAYER_PLAYING,
} anim_player_state_t;

typedef struct {
    bool in_use;
    emoji_anim_type_t type;
    uint32_t generation_id;
    anim_stream_t stream;
    anim_frame_buffer_t slots[WATCHER_ANIM_RING_FRAMES];
    int slot_frame_index[WATCHER_ANIM_RING_FRAMES];
    int slot_count;
    int current_slot;
    int current_frame_index;
    int buffered_frames;
    int next_frame_to_load;
    int next_slot_to_load;
} anim_playback_t;

static lv_obj_t *g_front_img = NULL;
static lv_obj_t *g_back_img = NULL;
static lv_timer_t *g_frame_timer = NULL;
static lv_timer_t *g_service_timer = NULL;
static TaskHandle_t g_worker_task = NULL;
static SemaphoreHandle_t g_player_mutex = NULL;

static anim_player_state_t g_state = ANIM_PLAYER_IDLE;
static anim_playback_t g_active_playback = {0};
static anim_playback_t g_pending_playback = {0};
static anim_frame_buffer_t g_static_frame = {0};
static emoji_anim_type_t g_current_type = EMOJI_ANIM_NONE;
static emoji_anim_type_t g_requested_type = EMOJI_ANIM_NONE;
static uint32_t g_latest_generation = 0;
static uint32_t g_override_interval_ms = 0;
static int64_t g_next_frame_deadline_us = 0;

static void anim_worker_task(void *param);
static void anim_frame_timer_cb(lv_timer_t *timer);
static void anim_service_timer_cb(lv_timer_t *timer);

static int min_int(int lhs, int rhs) {
    return lhs < rhs ? lhs : rhs;
}

static int effective_delay_ms(anim_playback_t *playback, int frame_index) {
    if (g_override_interval_ms > 0) {
        return (int)g_override_interval_ms;
    }

    int delay_ms = anim_stream_get_frame_delay_ms(&playback->stream, frame_index);
    return delay_ms > 0 ? delay_ms : EMOJI_ANIM_INTERVAL_MS;
}

static void configure_anim_layer(lv_obj_t *img_obj) {
    if (img_obj == NULL) {
        return;
    }

    lv_obj_set_size(img_obj, ANIM_SOURCE_FRAME_SIZE, ANIM_SOURCE_FRAME_SIZE);
    lv_img_set_pivot(img_obj, ANIM_SOURCE_FRAME_PIVOT, ANIM_SOURCE_FRAME_PIVOT);
    lv_img_set_zoom(img_obj, ANIM_DISPLAY_ZOOM_2X);
    lv_img_set_antialias(img_obj, false);
}

static void hide_back_layer(void) {
    if (g_back_img != NULL) {
        lv_obj_add_flag(g_back_img, LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_style_opa(g_back_img, LV_OPA_TRANSP, 0);
    }
    if (g_front_img != NULL) {
        lv_obj_set_style_opa(g_front_img, LV_OPA_COVER, 0);
    }
}

static void playback_reset_slots(anim_playback_t *playback) {
    for (int index = 0; index < WATCHER_ANIM_RING_FRAMES; ++index) {
        playback->slot_frame_index[index] = -1;
    }
}

static void playback_cleanup(anim_playback_t *playback) {
    if (playback == NULL) {
        return;
    }

    anim_stream_close(&playback->stream);
    for (int index = 0; index < WATCHER_ANIM_RING_FRAMES; ++index) {
        anim_frame_buffer_free(&playback->slots[index]);
    }
    memset(playback, 0, sizeof(*playback));
    playback_reset_slots(playback);
}

static int playback_open(anim_playback_t *playback, emoji_anim_type_t type, uint32_t generation_id) {
    memset(playback, 0, sizeof(*playback));
    playback_reset_slots(playback);

    if (anim_stream_open(type, &playback->stream) != 0) {
        return -1;
    }

    playback->slot_count = min_int(WATCHER_ANIM_RING_FRAMES, playback->stream.frame_count > 0 ? playback->stream.frame_count : 1);
    playback->in_use = true;
    playback->type = type;
    playback->generation_id = generation_id;
    playback->current_slot = 0;
    playback->current_frame_index = 0;
    playback->buffered_frames = 0;
    playback->next_frame_to_load = 0;
    playback->next_slot_to_load = 0;

    for (int index = 0; index < playback->slot_count; ++index) {
        if (anim_frame_buffer_init(&playback->slots[index], playback->stream.info.width, playback->stream.info.height) != 0) {
            playback_cleanup(playback);
            return -1;
        }
    }

    return 0;
}

static bool playback_fill_next(anim_playback_t *playback) {
    if (playback == NULL || !playback->in_use || playback->buffered_frames >= playback->slot_count) {
        return false;
    }

    int frame_count = playback->stream.frame_count;
    if (frame_count <= 0) {
        return false;
    }

    int frame_index = playback->next_frame_to_load;
    if (frame_index >= frame_count) {
        if (!playback->stream.info.loop) {
            return false;
        }
        frame_index %= frame_count;
        playback->next_frame_to_load = frame_index;
    }

    int slot_index = playback->next_slot_to_load;
    if (anim_stream_read_frame(&playback->stream, frame_index, &playback->slots[slot_index]) != 0) {
        ESP_LOGW(TAG, "Failed to read frame %d for %s", frame_index, emoji_type_name(playback->type));
        return false;
    }

    playback->slot_frame_index[slot_index] = frame_index;
    playback->buffered_frames++;
    playback->next_frame_to_load = frame_index + 1;
    playback->next_slot_to_load = (slot_index + 1) % playback->slot_count;
    return true;
}

static bool playback_advance(anim_playback_t *playback) {
    if (playback == NULL || !playback->in_use) {
        return false;
    }

    if (playback->buffered_frames <= 1) {
        return false;
    }

    int old_slot = playback->current_slot;
    int next_slot = (old_slot + 1) % playback->slot_count;
    if (playback->slot_frame_index[next_slot] < 0) {
        return false;
    }

    playback->slot_frame_index[old_slot] = -1;
    playback->current_slot = next_slot;
    playback->current_frame_index = playback->slot_frame_index[next_slot];
    playback->buffered_frames--;
    return true;
}

static const lv_img_dsc_t *playback_current_descriptor(anim_playback_t *playback) {
    if (playback == NULL || !playback->in_use || playback->current_slot < 0) {
        return NULL;
    }
    return &playback->slots[playback->current_slot].img_dsc;
}

static int ensure_worker_started(void) {
    if (g_player_mutex == NULL) {
        g_player_mutex = xSemaphoreCreateMutex();
        if (g_player_mutex == NULL) {
            return -1;
        }
    }

    if (g_worker_task == NULL) {
        BaseType_t rc = xTaskCreate(anim_worker_task, "anim_stream", 6144, NULL, 5, &g_worker_task);
        if (rc != pdPASS) {
            g_worker_task = NULL;
            return -1;
        }
    }

    return 0;
}

static int commit_pending_playback(void) {
    if (!g_pending_playback.in_use || g_pending_playback.buffered_frames <= 0) {
        return -1;
    }

    if (playback_current_descriptor(&g_pending_playback) == NULL) {
        return -1;
    }

    playback_cleanup(&g_active_playback);
    g_active_playback = g_pending_playback;
    memset(&g_pending_playback, 0, sizeof(g_pending_playback));
    playback_reset_slots(&g_pending_playback);

    const lv_img_dsc_t *active_frame = playback_current_descriptor(&g_active_playback);
    if (active_frame == NULL) {
        playback_cleanup(&g_active_playback);
        g_state = ANIM_PLAYER_IDLE;
        g_current_type = EMOJI_ANIM_NONE;
        g_requested_type = EMOJI_ANIM_NONE;
        return -1;
    }

    if (g_front_img != NULL) {
        lv_img_set_src(g_front_img, active_frame);
        lv_obj_set_style_opa(g_front_img, LV_OPA_COVER, 0);
    }
    hide_back_layer();

    g_state = ANIM_PLAYER_PLAYING;
    g_current_type = g_active_playback.type;
    g_requested_type = g_active_playback.type;
    g_next_frame_deadline_us =
        esp_timer_get_time() + (int64_t)effective_delay_ms(&g_active_playback, g_active_playback.current_frame_index) * 1000LL;
    if (g_frame_timer != NULL && g_active_playback.stream.frame_count > 1) {
        lv_timer_resume(g_frame_timer);
    } else if (g_frame_timer != NULL) {
        lv_timer_pause(g_frame_timer);
    }

    ESP_LOGI(TAG, "Animation switch committed: %s", emoji_type_name(g_current_type));
    return 0;
}

static void anim_worker_task(void *param) {
    (void)param;

    for (;;) {
        bool did_work = false;

        if (g_player_mutex != NULL && xSemaphoreTake(g_player_mutex, portMAX_DELAY) == pdTRUE) {
            if (g_pending_playback.in_use && g_pending_playback.buffered_frames < g_pending_playback.slot_count) {
                did_work = playback_fill_next(&g_pending_playback);
            } else if (g_active_playback.in_use && g_active_playback.buffered_frames < g_active_playback.slot_count) {
                did_work = playback_fill_next(&g_active_playback);
            }
            xSemaphoreGive(g_player_mutex);
        }

        if (!did_work) {
            vTaskDelay(pdMS_TO_TICKS(ANIM_WORKER_IDLE_MS));
        }
    }
}

static void anim_frame_timer_cb(lv_timer_t *timer) {
    (void)timer;

    if (g_state != ANIM_PLAYER_PLAYING || g_current_type == EMOJI_ANIM_NONE || g_player_mutex == NULL) {
        return;
    }

    int64_t now_us = esp_timer_get_time();
    if (now_us < g_next_frame_deadline_us) {
        return;
    }

    if (xSemaphoreTake(g_player_mutex, 0) != pdTRUE) {
        return;
    }

    if (playback_advance(&g_active_playback)) {
        const lv_img_dsc_t *frame = playback_current_descriptor(&g_active_playback);
        if (frame != NULL && g_front_img != NULL) {
            lv_img_set_src(g_front_img, frame);
        }
        g_current_type = g_active_playback.type;
        g_next_frame_deadline_us =
            now_us + (int64_t)effective_delay_ms(&g_active_playback, g_active_playback.current_frame_index) * 1000LL;
    } else {
        g_next_frame_deadline_us = now_us + (int64_t)ANIM_TIMER_TICK_MS * 1000LL;
    }

    xSemaphoreGive(g_player_mutex);
}

static void anim_service_timer_cb(lv_timer_t *timer) {
    (void)timer;

    if (g_state != ANIM_PLAYER_SWITCH_PREPARING || g_player_mutex == NULL) {
        return;
    }

    if (xSemaphoreTake(g_player_mutex, 0) != pdTRUE) {
        return;
    }

    int required_frames = g_active_playback.in_use ? min_int(2, g_pending_playback.slot_count) : 1;
    if (g_pending_playback.in_use && g_pending_playback.buffered_frames >= required_frames) {
        commit_pending_playback();
    }

    xSemaphoreGive(g_player_mutex);
}

int emoji_anim_init(lv_obj_t *img_obj) {
    if (img_obj == NULL) {
        ESP_LOGE(TAG, "Invalid image object");
        return -1;
    }

    if (anim_catalog_init() != 0) {
        ESP_LOGW(TAG, "Animation catalog init failed");
    }

    g_front_img = img_obj;
    g_current_type = EMOJI_ANIM_NONE;
    g_requested_type = EMOJI_ANIM_NONE;
    g_state = ANIM_PLAYER_IDLE;
    g_latest_generation = 0;
    g_next_frame_deadline_us = 0;

    lvgl_port_lock(0);

    lv_obj_t *parent = lv_obj_get_parent(img_obj);
    configure_anim_layer(g_front_img);
    if (g_back_img == NULL && parent != NULL) {
        g_back_img = lv_img_create(parent);
        lv_obj_set_pos(g_back_img, lv_obj_get_x(img_obj), lv_obj_get_y(img_obj));
        configure_anim_layer(g_back_img);
    }
    hide_back_layer();

    if (g_frame_timer == NULL) {
        g_frame_timer = lv_timer_create(anim_frame_timer_cb, ANIM_TIMER_TICK_MS, NULL);
        lv_timer_pause(g_frame_timer);
    }
    if (g_service_timer == NULL) {
        g_service_timer = lv_timer_create(anim_service_timer_cb, ANIM_TIMER_TICK_MS, NULL);
    }

    lvgl_port_unlock();

    if (ensure_worker_started() != 0) {
        ESP_LOGW(TAG, "Failed to start animation stream worker");
    }
    return 0;
}

int emoji_anim_start(emoji_anim_type_t type) {
    if (g_front_img == NULL) {
        ESP_LOGE(TAG, "Animation not initialized");
        return -1;
    }
    if (!anim_catalog_has_type(type)) {
        ESP_LOGW(TAG, "Animation type unavailable: %s", emoji_type_name(type));
        return -1;
    }
    if (g_player_mutex == NULL && ensure_worker_started() != 0) {
        return -1;
    }
    if (g_player_mutex == NULL || xSemaphoreTake(g_player_mutex, portMAX_DELAY) != pdTRUE) {
        return -1;
    }

    if (g_active_playback.in_use && g_active_playback.type == type && g_state == ANIM_PLAYER_PLAYING) {
        xSemaphoreGive(g_player_mutex);
        return 0;
    }
    if (g_pending_playback.in_use && g_pending_playback.type == type) {
        xSemaphoreGive(g_player_mutex);
        return 0;
    }

    playback_cleanup(&g_pending_playback);
    ++g_latest_generation;

    if (playback_open(&g_pending_playback, type, g_latest_generation) != 0) {
        xSemaphoreGive(g_player_mutex);
        return -1;
    }

    g_requested_type = type;
    g_state = ANIM_PLAYER_SWITCH_PREPARING;

    if (!g_active_playback.in_use) {
        /* First animation switch should show something as soon as the first frame is ready. */
        (void)playback_fill_next(&g_pending_playback);
        if (g_pending_playback.buffered_frames > 0) {
            commit_pending_playback();
        }
    }

    xSemaphoreGive(g_player_mutex);
    return 0;
}

void emoji_anim_stop(void) {
    if (g_player_mutex != NULL && xSemaphoreTake(g_player_mutex, portMAX_DELAY) == pdTRUE) {
        playback_cleanup(&g_active_playback);
        playback_cleanup(&g_pending_playback);
        xSemaphoreGive(g_player_mutex);
    }

    if (g_frame_timer != NULL) {
        lv_timer_pause(g_frame_timer);
    }
    hide_back_layer();
    g_state = ANIM_PLAYER_IDLE;
    g_current_type = EMOJI_ANIM_NONE;
    g_requested_type = EMOJI_ANIM_NONE;
    g_next_frame_deadline_us = 0;
}

bool emoji_anim_is_running(void) {
    return g_state == ANIM_PLAYER_PLAYING && g_current_type != EMOJI_ANIM_NONE;
}

bool emoji_anim_is_switch_pending(void) {
    return g_state == ANIM_PLAYER_SWITCH_PREPARING;
}

emoji_anim_type_t emoji_anim_get_type(void) {
    return g_current_type;
}

void emoji_anim_set_interval(uint32_t interval_ms) {
    g_override_interval_ms = interval_ms;
}

int emoji_anim_show_static(emoji_anim_type_t type, int frame) {
    if (g_front_img == NULL) {
        return -1;
    }

    emoji_anim_stop();
    if (anim_load_static_frame(type, frame, &g_static_frame) != 0) {
        return -1;
    }

    lv_img_set_src(g_front_img, &g_static_frame.img_dsc);
    lv_obj_set_style_opa(g_front_img, LV_OPA_COVER, 0);
    hide_back_layer();
    g_current_type = type;
    return 0;
}

int emoji_anim_prefetch_type(emoji_anim_type_t type) {
    return anim_catalog_has_type(type) ? 0 : -1;
}

int emoji_anim_get_fps(void) {
    uint32_t interval_ms = g_override_interval_ms > 0 ? g_override_interval_ms : EMOJI_ANIM_INTERVAL_MS;
    return interval_ms > 0 ? (int)(1000U / interval_ms) : 0;
}

void emoji_anim_set_fps(int fps) {
    if (fps < 1) {
        fps = 1;
    } else if (fps > 60) {
        fps = 60;
    }
    emoji_anim_set_interval((uint32_t)(1000 / fps));
}
