from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Iterator

from .api import WanClient
from .config import SETTINGS
from .database import create_task, get_task, list_tasks, pending_tasks, update_task
from .media import normalize_files, persist_files, validate_audio, validate_image, validate_video

MODES = ["文生视频", "首帧图生视频", "首尾帧生视频", "图片+视频多模态参考生视频", "视频编辑", "视频延长"]


def _validate_seed(seed: float | int | None) -> int:
    value = int(seed if seed is not None else -1)
    if value != -1 and not 0 <= value <= 2147483647:
        raise ValueError("随机种子须为 -1 或 0–2147483647。")
    return value


def prepare(mode: str, images: Any, videos: Any, audios: Any, first: Any, last: Any, prompt: str,
            resolution: str, ratio: str, smart_duration: bool, duration: float,
            audio: bool, seed: float, prompt_extend: bool, persist: bool = True) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    if mode not in MODES:
        raise ValueError("未知生成模式。")
    if not prompt or not prompt.strip():
        raise ValueError("请输入提示词。")
    image_paths = normalize_files(images)
    video_paths = normalize_files(videos)
    audio_paths = normalize_files(audios)
    first_paths = normalize_files(first)
    last_paths = normalize_files(last)
    if len(image_paths) > 10 or len(video_paths) > 5 or len(audio_paths) > 5:
        raise ValueError("素材数量超限：图片最多10张，视频/音频最多5段。")
    frame_mode = mode in {"首帧图生视频", "首尾帧生视频"}
    if frame_mode and (image_paths or video_paths or audio_paths):
        raise ValueError("首尾帧模式不能与多模态参考素材混用。")
    if not frame_mode and (first_paths or last_paths):
        raise ValueError("当前模式不能使用首帧或尾帧素材。")
    if mode == "文生视频" and (image_paths or video_paths or audio_paths):
        raise ValueError("文生视频模式不接收任何素材。")
    if mode == "首帧图生视频" and (len(first_paths) != 1 or last_paths):
        raise ValueError("首帧图生视频必须且只能上传一张首帧图片。")
    if mode == "首尾帧生视频" and (len(first_paths) != 1 or len(last_paths) != 1):
        raise ValueError("首尾帧生视频必须各上传一张首帧和尾帧图片。")
    if mode == "图片+视频多模态参考生视频" and not (image_paths or video_paths):
        raise ValueError("多模态参考模式至少上传一张图片或一段视频。")
    if mode in {"视频编辑", "视频延长"} and not video_paths:
        raise ValueError(f"{mode}至少需要一段参考视频。")

    for path in image_paths + first_paths + last_paths:
        validate_image(path)
    video_total = sum(validate_video(path) for path in video_paths)
    audio_total = sum(validate_audio(path) for path in audio_paths)
    if video_total > 15.01:
        raise ValueError("参考视频总时长不能超过15秒。")
    if audio_total > 15.01:
        raise ValueError("参考音频总时长不能超过15秒。")
    output_duration = -1 if smart_duration else int(duration)
    if output_duration != -1 and not 2 <= output_duration <= 30:
        raise ValueError("生成时长须为2–30秒，或使用智能时长。")
    if video_paths and output_duration != -1 and video_total + output_duration > 30.01:
        raise ValueError(f"输入视频共 {video_total:.1f} 秒，输入+输出必须不超过30秒。")

    saved_images = persist_files(image_paths) if persist else image_paths
    saved_videos = persist_files(video_paths) if persist else video_paths
    saved_audios = persist_files(audio_paths) if persist else audio_paths
    saved_first = persist_files(first_paths) if persist else first_paths
    saved_last = persist_files(last_paths) if persist else last_paths
    media: list[dict[str, Any]] = []
    media.extend({"type": "reference_image", "path": str(p), "label": f"图片{i}"} for i, p in enumerate(saved_images, 1))
    media.extend({"type": "reference_video", "path": str(p), "label": f"视频{i}", "duration": round(validate_video(p), 3)} for i, p in enumerate(saved_videos, 1))
    media.extend({"type": "reference_audio", "path": str(p), "label": f"音频{i}", "duration": round(validate_audio(p), 3)} for i, p in enumerate(saved_audios, 1))
    media.extend({"type": "first_frame", "path": str(p), "label": "首帧"} for p in saved_first)
    media.extend({"type": "last_frame", "path": str(p), "label": "尾帧"} for p in saved_last)
    config = {"model": SETTINGS.model, "resolution": resolution, "ratio": ratio, "duration": output_duration, "audio": bool(audio), "seed": _validate_seed(seed), "prompt_extend": bool(prompt_extend), "watermark": False}
    summary = {"模式": mode, "提示词": prompt.strip(), "素材": [m["label"] for m in media], **config, "运行方式": "模拟 API（不收费）" if SETTINGS.mock_api else "真实 API（将产生费用）"}
    return config, media, summary


def build_payload(prompt: str, config: dict[str, Any], remote_media: list[dict[str, str]]) -> dict[str, Any]:
    parameters = {key: config[key] for key in ("resolution", "ratio", "duration", "audio", "seed", "prompt_extend", "watermark")}
    payload: dict[str, Any] = {"model": config["model"], "input": {"prompt": prompt.strip()}, "parameters": parameters}
    if remote_media:
        payload["input"]["media"] = remote_media
    return payload


def redact(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return re.sub(r"sk-[A-Za-z0-9_-]+", "***", text)


def run_generation(mode: str, images: Any, videos: Any, audios: Any, first: Any, last: Any, prompt: str,
                   resolution: str, ratio: str, smart_duration: bool, duration: float, audio: bool,
                   seed: float, prompt_extend: bool, confirmed: bool) -> Iterator[tuple[str, str | None, str | None, list[list[Any]], int | None]]:
    if not confirmed:
        yield ("尚未提交：请先点击“1. 校验并显示生成配置”，核对后勾选“我已核对配置，确认提交”。", None, None, history_rows(), None)
        return
    try:
        config, media, _ = prepare(mode, images, videos, audios, first, last, prompt, resolution, ratio, smart_duration, duration, audio, seed, prompt_extend)
        if not SETTINGS.mock_api:
            SETTINGS.validate_real_api()
    except ValueError as exc:
        yield (f"尚未提交：{exc}", None, None, history_rows(), None)
        return
    client = WanClient(SETTINGS)
    local_id = create_task(mode, prompt.strip(), config, media, {}, "PENDING")
    yield (f"正在上传素材…（本地任务 #{local_id}）", None, None, history_rows(), local_id)
    try:
        remote_media = [{"type": item["type"], "url": client.upload(Path(item["path"]))} for item in media]
        payload = build_payload(prompt, config, remote_media)
        update_task(local_id, request_json=redact(payload), status="PENDING")
        remote_id = client.submit(payload)
        update_task(local_id, remote_task_id=remote_id, status="RUNNING", message="任务已提交")
        yield (f"任务 ID：{remote_id}\n状态：处理中", None, None, history_rows(), local_id)
        while True:
            result = client.query(remote_id)
            status = result["status"]
            if status == "SUCCEEDED":
                output = client.download(result["output_url"], remote_id)
                update_task(local_id, status="SUCCEEDED", output_path=str(output), output_url=result["output_url"], message="生成成功")
                yield (f"任务 ID：{remote_id}\n状态：生成成功，已保存到本地", str(output), str(output), history_rows(), local_id)
                return
            if status in {"FAILED", "CANCELED", "UNKNOWN"}:
                message = result.get("message") or "云端任务失败，请检查请求记录与素材。"
                update_task(local_id, status=status, message=message)
                yield (f"任务 ID：{remote_id}\n状态：{status}\n错误：{message}", None, None, history_rows(), local_id)
                return
            update_task(local_id, status=status, message=result.get("message", ""))
            yield (f"任务 ID：{remote_id}\n状态：{status}", None, None, history_rows(), local_id)
            time.sleep(5)
    except Exception as exc:
        update_task(local_id, status="FAILED", message=str(exc))
        yield (f"生成失败：{exc}", None, None, history_rows(), local_id)


def history_rows() -> list[list[Any]]:
    labels = {"PENDING": "等待中", "RUNNING": "处理中", "SUCCEEDED": "成功", "FAILED": "失败", "CANCELED": "已取消"}
    return [[row["id"], row["created_at"], row["mode"], row["prompt"][:40], labels.get(row["status"], row["status"]), row["remote_task_id"]] for row in list_tasks()]


def restore(local_id: float | int | None) -> tuple[Any, ...]:
    if not local_id:
        raise ValueError("请在历史表中选择一行。")
    row = get_task(int(local_id))
    if not row:
        raise ValueError("历史任务不存在。")
    config = json.loads(row["config_json"])
    media = json.loads(row["media_json"])
    by_type: dict[str, list[str]] = {}
    for item in media:
        by_type.setdefault(item["type"], []).append(item["path"])
    return (row["mode"], by_type.get("reference_image", []), by_type.get("reference_video", []), by_type.get("reference_audio", []),
            (by_type.get("first_frame") or [None])[0], (by_type.get("last_frame") or [None])[0], row["prompt"], config["resolution"], config["ratio"],
            config["duration"] == -1, 5 if config["duration"] == -1 else config["duration"], config["audio"], config["seed"], config["prompt_extend"],
            row["output_path"] or None, row["output_path"] or None, f"已恢复本地任务 #{row['id']}（{row['status']}）")


def resume_pending_once() -> None:
    client = WanClient(SETTINGS)
    for row in pending_tasks():
        remote_id = row["remote_task_id"]
        if not remote_id:
            update_task(row["id"], status="FAILED", message="程序退出前尚未获得云端任务 ID。")
            continue
        try:
            result = client.query(remote_id)
            if result["status"] == "SUCCEEDED":
                output = client.download(result["output_url"], remote_id)
                update_task(row["id"], status="SUCCEEDED", output_path=str(output), output_url=result["output_url"], message="重启后恢复成功")
            elif result["status"] in {"FAILED", "CANCELED", "UNKNOWN"}:
                update_task(row["id"], status=result["status"], message=result.get("message", ""))
            else:
                # 后台继续等待，使程序重启后仍能自动取回最终视频。
                for _ in range(360):
                    time.sleep(10)
                    result = client.query(remote_id)
                    if result["status"] == "SUCCEEDED":
                        output = client.download(result["output_url"], remote_id)
                        update_task(row["id"], status="SUCCEEDED", output_path=str(output), output_url=result["output_url"], message="重启后恢复成功")
                        break
                    if result["status"] in {"FAILED", "CANCELED", "UNKNOWN"}:
                        update_task(row["id"], status=result["status"], message=result.get("message", ""))
                        break
                    update_task(row["id"], status=result["status"], message=result.get("message", ""))
        except Exception as exc:
            update_task(row["id"], message=f"恢复查询失败：{exc}")
