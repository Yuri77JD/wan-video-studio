from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests

from .config import OUTPUT_DIR, Settings


class WanApiError(RuntimeError):
    pass


class WanClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()

    def _headers(self, async_request: bool = False) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json", "X-DashScope-OssResourceResolve": "enable"}
        if async_request:
            headers["X-DashScope-Async"] = "enable"
        return headers

    def upload(self, path: Path) -> str:
        if self.settings.mock_api:
            return f"mock://{path.resolve()}"
        self.settings.validate_real_api()
        # 与生成任务使用同一个地域和业务空间入口。
        policy_endpoint = f"{self.settings.base_url}/uploads"
        response = self.session.get(policy_endpoint, headers={"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json"}, params={"action": "getPolicy", "model": self.settings.model}, timeout=30)
        self._raise(response, "获取上传凭证失败")
        policy = response.json()["data"]
        key = f"{policy['upload_dir']}/{uuid.uuid4().hex}_{path.name}"
        with path.open("rb") as stream:
            fields = {
                "OSSAccessKeyId": (None, policy["oss_access_key_id"]), "Signature": (None, policy["signature"]),
                "policy": (None, policy["policy"]), "x-oss-object-acl": (None, policy["x_oss_object_acl"]),
                "x-oss-forbid-overwrite": (None, policy["x_oss_forbid_overwrite"]), "key": (None, key),
                "success_action_status": (None, "200"), "file": (path.name, stream),
            }
            uploaded = self.session.post(policy["upload_host"], files=fields, timeout=300)
        self._raise(uploaded, f"上传 {path.name} 失败")
        return f"oss://{key}"

    def submit(self, payload: dict[str, Any]) -> str:
        if self.settings.mock_api:
            return f"mock-{uuid.uuid4().hex[:16]}"
        self.settings.validate_real_api()
        url = f"{self.settings.base_url}/services/aigc/video-generation/video-synthesis"
        response = self.session.post(url, headers=self._headers(True), json=payload, timeout=60)
        self._raise(response, "提交任务失败")
        data = response.json()
        task_id = data.get("output", {}).get("task_id")
        if not task_id:
            raise WanApiError(f"接口未返回任务 ID：{json.dumps(data, ensure_ascii=False)}")
        return task_id

    def query(self, task_id: str) -> dict[str, Any]:
        if self.settings.mock_api:
            return {"status": "SUCCEEDED", "output_url": "mock://generated"}
        url = f"{self.settings.base_url}/tasks/{task_id}"
        response = self.session.get(url, headers=self._headers(), timeout=30)
        self._raise(response, "查询任务失败")
        data = response.json()
        output = data.get("output", {})
        return {
            "status": output.get("task_status", "UNKNOWN"),
            "output_url": output.get("video_url") or output.get("results", [{}])[0].get("url", ""),
            "message": data.get("message") or output.get("message", ""),
            "raw": data,
        }

    def download(self, url: str, task_id: str) -> Path:
        target = OUTPUT_DIR / f"wan_{task_id}.mp4"
        if url.startswith("mock://"):
            self._make_mock_video(target)
            return target
        with self.session.get(url, stream=True, timeout=300) as response:
            self._raise(response, "下载生成视频失败")
            with target.open("wb") as stream:
                shutil.copyfileobj(response.raw, stream)
        return target

    @staticmethod
    def _raise(response: requests.Response, prefix: str) -> None:
        if response.ok:
            return
        try:
            data = response.json()
            detail = data.get("message") or data.get("code") or response.text
        except ValueError:
            detail = response.text
        raise WanApiError(f"{prefix}（HTTP {response.status_code}）：{detail}")

    @staticmethod
    def _make_mock_video(target: Path) -> None:
        writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"mp4v"), 24, (640, 360))
        if not writer.isOpened():
            raise WanApiError("本机 OpenCV 无法创建模拟 MP4。")
        for index in range(72):
            frame = np.full((360, 640, 3), (24, 20, 18), dtype=np.uint8)
            cv2.rectangle(frame, (40 + index * 4, 120), (180 + index * 4, 260), (190, 110, 40), -1)
            cv2.putText(frame, "Wan Video Studio - MOCK", (92, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (235, 235, 235), 2)
            cv2.putText(frame, "No paid API call was made", (145, 320), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (170, 170, 170), 1)
            writer.write(frame)
        writer.release()
