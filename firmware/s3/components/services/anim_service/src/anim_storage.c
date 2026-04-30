/**
 * @file anim_storage.c
 * @brief SD-backed animpack catalog and frame loading helpers.
 */

#include "anim_storage.h"
#include "anim_meta.h"

#include "esp_heap_caps.h"
#include "esp_log.h"

#include <errno.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>

#define TAG "ANIM_STORAGE"
#define ANIM_MANIFEST_VERSION 2U
#define ANIM_PACK_VERSION 2U
#define ANIM_MAX_LOOP_DURATION_MS (60 * 60 * 1000)

typedef struct __attribute__((packed)) {
    char magic[4];
    uint16_t version;
    uint16_t type_count;
} anim_manifest_header_t;

typedef struct __attribute__((packed)) {
    uint16_t type_id;
    uint16_t width;
    uint16_t height;
    uint16_t fps;
    uint16_t frame_count;
    uint8_t loop;
    uint8_t reserved[3];
    char name[24];
    char pack_path[ANIM_MAX_PATH_LEN];
} anim_manifest_entry_t;

typedef struct __attribute__((packed)) {
    char magic[4];
    uint16_t version;
    uint16_t width;
    uint16_t height;
    uint16_t frame_count;
    uint8_t loop;
    uint8_t reserved;
    uint16_t default_delay_ms;
    uint32_t toc_offset;
    uint32_t payload_offset;
    uint32_t frame_data_size;
} anim_pack_header_t;

static const char *k_manifest_magic = "ANIM";
static const char *k_pack_magic = "ANPK";
static const int k_frame_read_attempts = 3;

static const char *emoji_names[EMOJI_ANIM_COUNT] = {
    "boot",     "happy",    "error",      "bluetooth",     "speaking",    "listening",    "processing",
    "standby",  "thinking", "custom1",    "custom2",       "custom3",     "standby1",     "standby2",
    "standby3", "standby4", "disconnect", "shock",         "sunglasses",  "sad",          "get",
    "smile",    "recharge", "speechless", "concentration", "fondle_love", "fondle_anger", "blink",
};

static bool g_catalog_initialized = false;
static anim_catalog_type_info_t g_catalog[EMOJI_ANIM_COUNT];
static anim_frame_buffer_t g_legacy_frame = {0};

static void reset_catalog(void) {
    memset(g_catalog, 0, sizeof(g_catalog));
    for (int index = 0; index < EMOJI_ANIM_COUNT; ++index) {
        g_catalog[index].type = (emoji_anim_type_t)index;
        strncpy(g_catalog[index].name, emoji_names[index], sizeof(g_catalog[index].name) - 1);
        g_catalog[index].fps = (uint16_t)anim_meta_get_fps((emoji_anim_type_t)index);
        g_catalog[index].loop = anim_meta_should_loop((emoji_anim_type_t)index);
    }
}

static void normalize_pack_path(const char *src, char *dst, size_t dst_size) {
    if (dst == NULL || dst_size == 0) {
        return;
    }

    dst[0] = '\0';
    if (src == NULL || src[0] == '\0') {
        return;
    }

    if (src[0] == '/') {
        snprintf(dst, dst_size, "%s", src);
        return;
    }

    snprintf(dst, dst_size, "%s/%s", ANIM_STORAGE_ROOT, src);
}

static int anim_stream_reopen_file(anim_stream_t *stream) {
    if (stream == NULL || stream->info.pack_path[0] == '\0') {
        return -1;
    }

    FILE *reopened = fopen(stream->info.pack_path, "rb");
    if (reopened == NULL) {
        ESP_LOGW(TAG, "Failed to reopen animpack %s: errno=%d (%s)", stream->info.pack_path, errno, strerror(errno));
        return -1;
    }

    if (stream->file != NULL) {
        fclose(stream->file);
    }

    stream->file = reopened;
    return 0;
}

static int load_manifest_from_path(const char *manifest_path) {
    FILE *handle = fopen(manifest_path, "rb");
    if (handle == NULL) {
        ESP_LOGW(TAG, "Failed to open anim manifest %s: errno=%d (%s)", manifest_path, errno, strerror(errno));
        return -1;
    }

    anim_manifest_header_t header = {0};
    if (fread(&header, sizeof(header), 1, handle) != 1) {
        fclose(handle);
        return -1;
    }

    if (memcmp(header.magic, k_manifest_magic, sizeof(header.magic)) != 0 || header.version != ANIM_MANIFEST_VERSION) {
        ESP_LOGW(TAG, "Invalid animation manifest at %s", manifest_path);
        fclose(handle);
        return -1;
    }

    int loaded = 0;
    for (uint16_t index = 0; index < header.type_count; ++index) {
        anim_manifest_entry_t entry = {0};
        if (fread(&entry, sizeof(entry), 1, handle) != 1) {
            break;
        }

        if (entry.type_id >= EMOJI_ANIM_COUNT || entry.frame_count == 0) {
            continue;
        }

        anim_catalog_type_info_t *info = &g_catalog[entry.type_id];
        info->available = true;
        info->width = entry.width;
        info->height = entry.height;
        info->fps = entry.fps > 0 ? entry.fps : (uint16_t)anim_meta_get_fps((emoji_anim_type_t)entry.type_id);
        info->loop = entry.loop != 0;
        info->frame_count = entry.frame_count;
        if (entry.name[0] != '\0') {
            strncpy(info->name, entry.name, sizeof(info->name) - 1);
        }
        normalize_pack_path(entry.pack_path, info->pack_path, sizeof(info->pack_path));
        ++loaded;
    }

    fclose(handle);
    if (loaded > 0) {
        ESP_LOGI(TAG, "Loaded animpack manifest from %s (%d types)", manifest_path, loaded);
        return 0;
    }
    return -1;
}

static int ensure_manifest_loaded(void) {
    if (g_catalog_initialized) {
        return 0;
    }

    anim_meta_init();
    reset_catalog();
    if (load_manifest_from_path(ANIM_MANIFEST_PATH) != 0 && load_manifest_from_path(ANIM_MANIFEST_FALLBACK_PATH) != 0) {
        ESP_LOGW(TAG, "No SD animation manifest available under %s", ANIM_STORAGE_ROOT);
        return -1;
    }

    g_catalog_initialized = true;
    return 0;
}

static int anim_frame_buffer_ensure(anim_frame_buffer_t *buffer, uint16_t width, uint16_t height) {
    size_t expected_size = (size_t)width * (size_t)height * 2U;
    if (buffer == NULL || expected_size == 0) {
        return -1;
    }

    if (buffer->img_data != NULL && buffer->data_size == expected_size && buffer->width == width &&
        buffer->height == height) {
        return 0;
    }

    anim_frame_buffer_free(buffer);
    return anim_frame_buffer_init(buffer, width, height);
}

int emoji_spiffs_init(void) {
    /* Legacy compatibility no-op. Animation assets now live on SD card. */
    return 0;
}

int anim_catalog_init(void) {
    return ensure_manifest_loaded();
}

const anim_catalog_type_info_t *anim_catalog_get_type_info(emoji_anim_type_t type) {
    if (ensure_manifest_loaded() != 0) {
        return NULL;
    }
    if (type < 0 || type >= EMOJI_ANIM_COUNT) {
        return NULL;
    }
    return &g_catalog[type];
}

bool anim_catalog_has_type(emoji_anim_type_t type) {
    const anim_catalog_type_info_t *info = anim_catalog_get_type_info(type);
    return info != NULL && info->available && info->pack_path[0] != '\0' && info->frame_count > 0;
}

int emoji_load_type(emoji_anim_type_t type) {
    const anim_catalog_type_info_t *info = anim_catalog_get_type_info(type);
    return info != NULL && info->available ? info->frame_count : -1;
}

int emoji_get_frame_count(emoji_anim_type_t type) {
    const anim_catalog_type_info_t *info = anim_catalog_get_type_info(type);
    if (info == NULL || !info->available) {
        return 0;
    }

    anim_config_t *cfg = anim_meta_get_config(type);
    if (cfg->frame_count > 0 && cfg->frame_count < info->frame_count) {
        return cfg->frame_count;
    }
    return info->frame_count;
}

int emoji_get_loop_duration_ms(emoji_anim_type_t type) {
    const anim_catalog_type_info_t *info = anim_catalog_get_type_info(type);
    if (info == NULL || !info->available || info->frame_count == 0) {
        return 0;
    }

    anim_stream_t stream = {0};
    int64_t duration_ms = 0;
    if (anim_stream_open(type, &stream) == 0) {
        int frame_count = emoji_get_frame_count(type);
        if (frame_count <= 0 || frame_count > stream.frame_count) {
            frame_count = stream.frame_count;
        }
        for (int frame = 0; frame < frame_count; ++frame) {
            int delay_ms = anim_stream_get_frame_delay_ms(&stream, frame);
            if (delay_ms > 0) {
                duration_ms += delay_ms;
                if (duration_ms > ANIM_MAX_LOOP_DURATION_MS) {
                    ESP_LOGW(TAG, "Loop duration for %s exceeds cap; clamping to %dms", info->name,
                             ANIM_MAX_LOOP_DURATION_MS);
                    duration_ms = ANIM_MAX_LOOP_DURATION_MS;
                    break;
                }
            }
        }
        anim_stream_close(&stream);
        if (duration_ms > 0) {
            return (int)duration_ms;
        }
    }

    int fps = info->fps > 0 ? info->fps : anim_meta_get_fps(type);
    if (fps <= 0) {
        fps = anim_meta_get_default_fps();
    }
    if (fps <= 0) {
        return 0;
    }
    int64_t fallback_duration_ms = ((int64_t)emoji_get_frame_count(type) * 1000LL) / fps;
    if (fallback_duration_ms <= 0) {
        return 0;
    }
    if (fallback_duration_ms > ANIM_MAX_LOOP_DURATION_MS) {
        ESP_LOGW(TAG, "Fallback loop duration for %s exceeds cap; clamping to %dms", info->name,
                 ANIM_MAX_LOOP_DURATION_MS);
        return ANIM_MAX_LOOP_DURATION_MS;
    }
    if (fallback_duration_ms > INT_MAX) {
        return INT_MAX;
    }
    return (int)fallback_duration_ms;
}

const char *emoji_type_name(emoji_anim_type_t type) {
    if (type < 0 || type >= EMOJI_ANIM_COUNT) {
        return "unknown";
    }
    return emoji_names[type];
}

int anim_frame_buffer_init(anim_frame_buffer_t *buffer, uint16_t width, uint16_t height) {
    if (buffer == NULL || width == 0 || height == 0) {
        return -1;
    }

    size_t data_size = (size_t)width * (size_t)height * 2U;
    uint8_t *img_data = (uint8_t *)heap_caps_malloc(data_size, MALLOC_CAP_SPIRAM);
    if (img_data == NULL) {
        ESP_LOGE(TAG, "Failed to allocate %u bytes for animation frame buffer", (unsigned)data_size);
        return -1;
    }

    memset(buffer, 0, sizeof(*buffer));
    buffer->img_data = img_data;
    buffer->data_size = data_size;
    buffer->width = width;
    buffer->height = height;
    buffer->color_format = LV_IMG_CF_TRUE_COLOR;
    buffer->img_dsc.header.always_zero = 0;
    buffer->img_dsc.header.w = width;
    buffer->img_dsc.header.h = height;
    buffer->img_dsc.header.cf = LV_IMG_CF_TRUE_COLOR;
    buffer->img_dsc.data_size = (uint32_t)data_size;
    buffer->img_dsc.data = img_data;
    return 0;
}

void anim_frame_buffer_free(anim_frame_buffer_t *buffer) {
    if (buffer == NULL) {
        return;
    }

    if (buffer->img_data != NULL) {
        heap_caps_free(buffer->img_data);
    }
    memset(buffer, 0, sizeof(*buffer));
}

int anim_stream_open(emoji_anim_type_t type, anim_stream_t *out_stream) {
    const anim_catalog_type_info_t *catalog_info = anim_catalog_get_type_info(type);
    if (catalog_info == NULL || !catalog_info->available || catalog_info->pack_path[0] == '\0' || out_stream == NULL) {
        return -1;
    }

    FILE *handle = fopen(catalog_info->pack_path, "rb");
    if (handle == NULL) {
        ESP_LOGW(TAG, "Failed to open animpack: %s", catalog_info->pack_path);
        return -1;
    }

    anim_pack_header_t header = {0};
    if (fread(&header, sizeof(header), 1, handle) != 1) {
        fclose(handle);
        return -1;
    }

    if (memcmp(header.magic, k_pack_magic, sizeof(header.magic)) != 0 || header.version != ANIM_PACK_VERSION) {
        ESP_LOGW(TAG, "Invalid animpack header: %s", catalog_info->pack_path);
        fclose(handle);
        return -1;
    }

    size_t table_size = (size_t)header.frame_count * sizeof(anim_pack_frame_desc_t);
    anim_pack_frame_desc_t *frames = (anim_pack_frame_desc_t *)malloc(table_size);
    if (frames == NULL) {
        fclose(handle);
        return -1;
    }

    if (fseek(handle, (long)header.toc_offset, SEEK_SET) != 0 ||
        fread(frames, sizeof(anim_pack_frame_desc_t), header.frame_count, handle) != header.frame_count) {
        free(frames);
        fclose(handle);
        return -1;
    }

    memset(out_stream, 0, sizeof(*out_stream));
    out_stream->file = handle;
    out_stream->info = *catalog_info;
    out_stream->info.width = header.width;
    out_stream->info.height = header.height;
    out_stream->info.frame_count = header.frame_count;
    out_stream->info.loop = header.loop != 0;
    out_stream->frames = frames;
    out_stream->frame_count = header.frame_count;
    out_stream->payload_offset = header.payload_offset;
    out_stream->frame_data_size = header.frame_data_size;
    return 0;
}

void anim_stream_close(anim_stream_t *stream) {
    if (stream == NULL) {
        return;
    }

    if (stream->file != NULL) {
        fclose(stream->file);
    }
    if (stream->frames != NULL) {
        free(stream->frames);
    }
    memset(stream, 0, sizeof(*stream));
}

int anim_stream_get_frame_delay_ms(const anim_stream_t *stream, int frame_index) {
    if (stream == NULL || stream->frames == NULL || frame_index < 0 || frame_index >= stream->frame_count) {
        return 0;
    }

    int delay_ms = stream->frames[frame_index].delay_ms;
    if (delay_ms > 0) {
        return delay_ms;
    }

    if (stream->info.fps > 0) {
        return 1000 / stream->info.fps;
    }

    return 1000 / anim_meta_get_default_fps();
}

int anim_stream_read_frame(anim_stream_t *stream, int frame_index, anim_frame_buffer_t *buffer) {
    if (stream == NULL || stream->file == NULL || stream->frames == NULL || buffer == NULL) {
        return -1;
    }
    if (frame_index < 0 || frame_index >= stream->frame_count) {
        return -1;
    }

    if (anim_frame_buffer_ensure(buffer, stream->info.width, stream->info.height) != 0) {
        return -1;
    }

    anim_pack_frame_desc_t *frame = &stream->frames[frame_index];
    if (frame->size > buffer->data_size) {
        ESP_LOGW(TAG, "Frame payload too large for buffer: %u > %u", (unsigned)frame->size,
                 (unsigned)buffer->data_size);
        return -1;
    }

    for (int attempt = 1; attempt <= k_frame_read_attempts; ++attempt) {
        errno = 0;
        clearerr(stream->file);

        if (fseek(stream->file, (long)(stream->payload_offset + frame->offset), SEEK_SET) == 0) {
            size_t bytes_read = fread(buffer->img_data, 1, frame->size, stream->file);
            if (bytes_read == frame->size) {
                buffer->img_dsc.data = buffer->img_data;
                buffer->img_dsc.data_size = (uint32_t)frame->size;
                return 0;
            }

            ESP_LOGW(TAG, "Short read for %s frame %d: got=%u expected=%u errno=%d ferror=%d feof=%d (attempt %d/%d)",
                     stream->info.name, frame_index, (unsigned)bytes_read, (unsigned)frame->size, errno,
                     ferror(stream->file), feof(stream->file), attempt, k_frame_read_attempts);
        } else {
            ESP_LOGW(TAG, "Failed to seek %s frame %d: errno=%d (%s) (attempt %d/%d)", stream->info.name, frame_index,
                     errno, strerror(errno), attempt, k_frame_read_attempts);
        }

        if (attempt < k_frame_read_attempts && anim_stream_reopen_file(stream) == 0) {
            continue;
        }
        break;
    }

    return -1;
}

int anim_load_static_frame(emoji_anim_type_t type, int frame_index, anim_frame_buffer_t *buffer) {
    anim_stream_t stream = {0};
    int result = -1;

    if (anim_stream_open(type, &stream) != 0) {
        return -1;
    }

    result = anim_stream_read_frame(&stream, frame_index, buffer);
    anim_stream_close(&stream);
    return result;
}

lv_img_dsc_t *emoji_get_image(emoji_anim_type_t type, int frame) {
    if (anim_load_static_frame(type, frame, &g_legacy_frame) != 0) {
        return NULL;
    }
    return &g_legacy_frame.img_dsc;
}

int emoji_load_all_images(void) {
    return emoji_load_all_images_with_cb(NULL);
}

int emoji_load_all_images_with_cb(emoji_progress_cb_t cb) {
    if (ensure_manifest_loaded() != 0) {
        return -1;
    }

    int total = 0;
    for (int type = 0; type < EMOJI_ANIM_COUNT; ++type) {
        if (!anim_catalog_has_type((emoji_anim_type_t)type)) {
            continue;
        }
        ++total;
        if (cb != NULL) {
            cb((emoji_anim_type_t)type, total, EMOJI_ANIM_COUNT);
        }
    }
    return total > 0 ? 0 : -1;
}

void emoji_free_all(void) {
    anim_frame_buffer_free(&g_legacy_frame);
}

bool emoji_images_loaded(void) {
    return false;
}
