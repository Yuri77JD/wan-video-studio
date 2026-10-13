from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

import cv2
from mutagen import File as MutagenFile
from PIL import Image

from .config import UPLOAD_DIR

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".mov"}
AUDIO_EXTS = {".wav", ".mp3"}


def normalize_files(value: Any) -> list[Path]:
    if not value:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    paths: list[Path] = []
    for item in values:
        raw = getattr(item, "name", item)
        if raw:
            paths.append(Path(str(raw)))
    return paths


def persist_files(paths: list[Path]) -> list[Path]:
    saved: list[Path] = []
    for source in paths:
        source = source.resolve()
        try:
            if source.is_relative_to(UPLOAD_DIR.resolve()):
                saved.append(source)
                continue
        except AttributeError:
            pass
        target = UPLOAD_DIR / f"{uuid.uuid4().hex}_{source.name}"
        shutil.copy2(source, target)
        saved.append(target)
    return saved


def media_duration(path: Path) -> float:
    if path.suffix.lower() in VIDEO_EXTS:
        cap = cv2.VideoCapture(str(path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        if fps <= 0 or frames <= 0:
            raise ValueError(f"无法读取视频时长：{path.name}")
        return frames / fps
    audio = MutagenFile(path)
    if not audio or not getattr(audio, "info", None):
        raise ValueError(f"无法读取音频时长：{path.name}")
    return float(audio.info.length)


def validate_image(path: Path) -> None:
    if path.suffix.lower() not in IMAGE_EXTS:
        raise ValueError(f"图片 {path.name} 格式不支持，仅支持 JPG/JPEG/PNG/BMP/WEBP。")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError(f"图片 {path.name} 超过 20MB。")
    with Image.open(path) as image:
        width, height = image.size
        if not 240 <= width <= 8000 or not 240 <= height <= 8000:
            raise ValueError(f"图片 {path.name} 单边须在 240–8000 像素。")
        if max(width / height, height / width) > 8:
            raise ValueError(f"图片 {path.name} 长宽比不能超过 8:1。")
        if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
            raise ValueError(f"图片 {path.name} 含透明通道，官方接口不支持。")


def validate_video(path: Path) -> float:
    if path.suffix.lower() not in VIDEO_EXTS:
        raise ValueError(f"视频 {path.name} 格式不支持，仅支持 MP4/MOV。")
    if path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError(f"视频 {path.name} 超过 100MB。")
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    if fps < 16:
        raise ValueError(f"视频 {path.name} 帧率须至少 16fps。")
    if not (240 <= width <= 4096 and 240 <= height <= 4096):
        raise ValueError(f"视频 {path.name} 单边须在 240–4096 像素。")
    if not width or not height or max(width / height, height / width) > 8:
        raise ValueError(f"视频 {path.name} 长宽比不能超过 8:1。")
    duration = frames / fps if fps else 0
    if not 1 <= duration <= 15:
        raise ValueError(f"视频 {path.name} 时长须在 1–15 秒。")
    return duration


def validate_audio(path: Path) -> float:
    if path.suffix.lower() not in AUDIO_EXTS:
        raise ValueError(f"音频 {path.name} 格式不支持，仅支持 WAV/MP3。")
    if path.stat().st_size > 15 * 1024 * 1024:
        raise ValueError(f"音频 {path.name} 超过 15MB。")
    duration = media_duration(path)
    if not 1 <= duration <= 15:
        raise ValueError(f"音频 {path.name} 时长须在 1–15 秒。")
    return duration

