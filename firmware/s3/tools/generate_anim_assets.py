#!/usr/bin/env python3
"""
Generate SD-card animation assets from a folder of GIF sources or legacy PNG sequences.

Outputs:
  - anim_manifest.bin (v2)
  - one <type>.animpack per animation

The firmware runtime treats GIF as an offline authoring format only. At build
time we expand each frame into a self-contained RGB565 payload that can be
streamed directly into a ring buffer on-device.
"""

from __future__ import annotations

import argparse
import re
import shutil
import struct
import sys
from pathlib import Path

try:
    from PIL import Image
    from PIL import ImageSequence
except ImportError as exc:  # pragma: no cover - runtime dependency check
    raise SystemExit("Pillow is required. Install it with: python -m pip install Pillow") from exc


PROJECT_VERSION = "v0.2.1"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_INPUT_DIR = PROJECT_ROOT / "assets" / "gif"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "release" / PROJECT_VERSION / "sdcard" / "anim"


ANIM_TYPES = [
    "boot",
    "happy",
    "error",
    "bluetooth",
    "speaking",
    "listening",
    "processing",
    "standby",
    "thinking",
    "custom1",
    "custom2",
    "custom3",
]

NAME_LEN = 24
PATH_LEN = 96
MANIFEST_MAGIC = b"ANIM"
MANIFEST_VERSION = 2
PACK_MAGIC = b"ANPK"
PACK_VERSION = 2
FRAME_DESC_FMT = "<IIHH"
FRAME_DESC_SIZE = struct.calcsize(FRAME_DESC_FMT)
MANIFEST_ENTRY_FMT = f"<HHHHHB3x{NAME_LEN}s{PATH_LEN}s"
PACK_HEADER_FMT = "<4sHHHHBBHIII"

LEGACY_IMPORT_MAP = {
    "watcher-boot": "boot",
    "watcher-error": "error",
    "watcher-happy": "happy",
    "watcher-bluetooth": "bluetooth",
    "watcher-listening": "listening",
    "watcher-processing": "processing",
    "watcher-custom1": "custom1",
    "watcher-custom2": "custom2",
    "watcher-custom3": "custom3",
    "watcher-processing2": "custom3",
    "watcher-speaking": "speaking",
    "watcher-standby": "standby",
    "watcher-thinking": "thinking",
}

GIF_CANDIDATES = {
    "boot": ["boot.gif", "watcher-boot.gif"],
    "happy": ["happy.gif", "watcher-happy.gif"],
    "error": ["error.gif", "watcher-error.gif"],
    "bluetooth": ["bluetooth.gif", "watcher-bluetooth.gif"],
    "speaking": ["speaking.gif", "watcher-speaking.gif"],
    "listening": ["listening.gif", "watcher-listening.gif"],
    "processing": ["processing.gif", "watcher-processing.gif"],
    "standby": ["standby.gif", "watcher-standby.gif"],
    "thinking": ["thinking.gif", "watcher-thinking.gif"],
    "custom1": ["custom1.gif", "watcher-custom1.gif"],
    "custom2": ["custom2.gif", "watcher-custom2.gif"],
    "custom3": ["custom3.gif", "watcher-custom3.gif", "watcher-processing2.gif"],
}


def encode_c_string(value: str, size: int) -> bytes:
    data = value.encode("utf-8")
    if len(data) >= size:
        raise ValueError(f"Value too long for fixed field ({size} bytes): {value}")
    return data + b"\0" * (size - len(data))


def extract_frame_index(stem: str) -> int:
    matches = re.findall(r"(\d+)", stem)
    if not matches:
        return 0
    return int(matches[-1])


def rgba_to_rgb565(image: Image.Image, swap_bytes: bool) -> bytes:
    rgba = image.convert("RGBA")
    payload = bytearray()
    rgba_bytes = rgba.tobytes()
    for offset in range(0, len(rgba_bytes), 4):
        r = rgba_bytes[offset]
        g = rgba_bytes[offset + 1]
        b = rgba_bytes[offset + 2]
        a = rgba_bytes[offset + 3]
        if a != 255:
            r = (r * a) // 255
            g = (g * a) // 255
            b = (b * a) // 255
        value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        payload += struct.pack(">H" if swap_bytes else "<H", value)
    return bytes(payload)


def load_gif_frames(path: Path, default_delay_ms: int) -> list[tuple[Image.Image, int]]:
    frames: list[tuple[Image.Image, int]] = []
    with Image.open(path) as image:
        fallback_delay = image.info.get("duration", default_delay_ms) or default_delay_ms
        for frame in ImageSequence.Iterator(image):
            delay_ms = frame.info.get("duration", fallback_delay) or default_delay_ms
            if delay_ms <= 0:
                delay_ms = default_delay_ms
            frames.append((frame.convert("RGBA").copy(), int(delay_ms)))
    return frames


def load_legacy_png_frames(path: Path, default_delay_ms: int) -> list[tuple[Image.Image, int]]:
    source_frames = sorted(path.glob("*.png"), key=lambda candidate: extract_frame_index(candidate.stem))
    frames: list[tuple[Image.Image, int]] = []
    for frame in source_frames:
        with Image.open(frame) as image:
            frames.append((image.convert("RGBA").copy(), default_delay_ms))
    return frames


def resolve_gif_source(import_dir: Path, anim_type: str) -> Path | None:
    candidate_names = GIF_CANDIDATES.get(anim_type, [])
    alias_stems = {anim_type.lower()}
    alias_stems.update(Path(candidate_name).stem.lower() for candidate_name in candidate_names)

    for candidate_name in candidate_names:
        candidate = import_dir / candidate_name
        if candidate.is_file():
            return candidate

    matches = [candidate for candidate in import_dir.rglob("*.gif") if candidate.stem.lower() in alias_stems]
    if not matches:
        return None

    matches.sort(key=lambda path: str(path.relative_to(import_dir)).lower())
    return matches[0]


def load_source_frames(import_dir: Path, anim_type: str, default_delay_ms: int) -> list[tuple[Image.Image, int]]:
    gif_source = resolve_gif_source(import_dir, anim_type)
    if gif_source is not None:
        return load_gif_frames(gif_source, default_delay_ms)

    legacy_dirs = [name for name, mapped_type in LEGACY_IMPORT_MAP.items() if mapped_type == anim_type]
    for legacy_dir in legacy_dirs:
        candidate = import_dir / legacy_dir
        if candidate.is_dir():
            frames = load_legacy_png_frames(candidate, default_delay_ms)
            if frames:
                return frames

    return []


def write_animpack(
    output_dir: Path,
    anim_type: str,
    frames: list[tuple[Image.Image, int]],
    default_fps: int,
    swap_bytes: bool,
) -> dict[str, int | str]:
    width, height = frames[0][0].size
    payloads = [rgba_to_rgb565(frame, swap_bytes) for frame, _ in frames]
    frame_data_size = len(payloads[0])
    if any(len(payload) != frame_data_size for payload in payloads):
        raise ValueError(f"Frame size mismatch in {anim_type}")

    pack_name = f"{anim_type}.animpack"
    pack_path = output_dir / pack_name
    toc_offset = struct.calcsize(PACK_HEADER_FMT)
    payload_offset = toc_offset + len(frames) * FRAME_DESC_SIZE
    default_delay_ms = max(1, int(round(1000 / max(default_fps, 1))))

    descriptors = []
    payload_offset_cursor = 0
    for payload, (_, delay_ms) in zip(payloads, frames):
        descriptors.append(struct.pack(FRAME_DESC_FMT, payload_offset_cursor, len(payload), delay_ms, 0))
        payload_offset_cursor += len(payload)

    header = struct.pack(
        PACK_HEADER_FMT,
        PACK_MAGIC,
        PACK_VERSION,
        width,
        height,
        len(frames),
        1,
        0,
        default_delay_ms,
        toc_offset,
        payload_offset,
        frame_data_size,
    )

    with pack_path.open("wb") as handle:
        handle.write(header)
        for descriptor in descriptors:
            handle.write(descriptor)
        for payload in payloads:
            handle.write(payload)

    return {
        "pack_name": pack_name,
        "width": width,
        "height": height,
        "frame_count": len(frames),
        "fps": default_fps,
    }


def build_manifest(
    import_dir: Path,
    output_dir: Path,
    default_fps: int,
    swap_bytes: bool,
    clean: bool,
) -> dict[str, int]:
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    default_delay_ms = max(1, int(round(1000 / max(default_fps, 1))))

    manifest_entries = []
    manifest_counts: dict[str, int] = {}
    for type_id, anim_type in enumerate(ANIM_TYPES):
        frames = load_source_frames(import_dir, anim_type, default_delay_ms)
        if not frames:
            continue

        pack_info = write_animpack(output_dir, anim_type, frames, default_fps, swap_bytes)
        entry = struct.pack(
            MANIFEST_ENTRY_FMT,
            type_id,
            pack_info["width"],
            pack_info["height"],
            pack_info["fps"],
            pack_info["frame_count"],
            1,
            encode_c_string(anim_type, NAME_LEN),
            encode_c_string(str(pack_info["pack_name"]), PATH_LEN),
        )
        manifest_entries.append(entry)
        manifest_counts[anim_type] = int(pack_info["frame_count"])

    manifest_path = output_dir / "anim_manifest.bin"
    manifest_path.write_bytes(
        struct.pack("<4sHH", MANIFEST_MAGIC, MANIFEST_VERSION, len(manifest_entries)) + b"".join(manifest_entries)
    )

    print(f"Wrote {manifest_path}")
    print(f"Generated {len(manifest_entries)} manifest entries in {output_dir}")
    for anim_type in ANIM_TYPES:
        if anim_type in manifest_counts:
            print(f"  {anim_type}: {manifest_counts[anim_type]} frame(s)")
    return manifest_counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        "--import-dir",
        dest="input_dir",
        default=str(DEFAULT_INPUT_DIR),
        help="Directory containing GIF sources or legacy PNG animation folders",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Where generated animpack assets should be written",
    )
    parser.add_argument("--fps", type=int, default=10, help="Default FPS stored in manifest entries")
    parser.add_argument(
        "--clean",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Remove the output directory contents before generating new assets",
    )
    parser.add_argument(
        "--lv-color-16-swap",
        action="store_true",
        help="Write RGB565 payloads in LVGL-native swapped 16-bit byte order",
    )
    args = parser.parse_args()

    import_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    if not import_dir.is_dir():
        raise SystemExit(f"Import directory does not exist: {import_dir}")

    build_manifest(import_dir, output_dir, args.fps, args.lv_color_16_swap, args.clean)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
