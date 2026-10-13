from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from wan_studio.api import WanClient
from wan_studio.config import Settings
from wan_studio.service import build_payload, run_generation


def test_payload_always_disables_watermark():
    config = {"model": "wan3.0-video", "resolution": "720P", "ratio": "16:9", "duration": 5, "audio": True, "seed": -1, "prompt_extend": True, "watermark": False}
    payload = build_payload("测试", config, [{"type": "reference_image", "url": "oss://x"}])
    assert payload["parameters"]["watermark"] is False
    assert payload["input"]["media"][0]["type"] == "reference_image"


def test_mock_video(tmp_path: Path):
    client = WanClient(Settings(mock_api=True))
    target = client.download("mock://generated", "unit-test")
    assert target.exists() and target.stat().st_size > 1000
    target.unlink()


def test_reference_image_and_video_mock_flow(tmp_path: Path, monkeypatch):
    import wan_studio.api as api_module
    import wan_studio.database as database_module
    import wan_studio.media as media_module
    import wan_studio.service as service_module

    monkeypatch.setattr(service_module, "SETTINGS", Settings(mock_api=True))
    monkeypatch.setattr(database_module, "DB_PATH", tmp_path / "history.db")
    monkeypatch.setattr(media_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(api_module, "OUTPUT_DIR", tmp_path / "outputs")
    (tmp_path / "uploads").mkdir()
    (tmp_path / "outputs").mkdir()
    database_module.init_db()

    image_path = tmp_path / "person.png"
    Image.new("RGB", (320, 320), "blue").save(image_path)
    video_path = tmp_path / "action.mp4"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 20, (320, 320))
    assert writer.isOpened()
    for _ in range(24):
        writer.write(np.zeros((320, 320, 3), dtype=np.uint8))
    writer.release()

    updates = list(run_generation(
        "图片+视频多模态参考生视频", [str(image_path)], [str(video_path)], [], None, None,
        "图片1中的人物模仿视频1的动作", "720P", "adaptive", False, 5, True, -1, True, True,
    ))
    assert "生成成功" in updates[-1][0]
    assert Path(updates[-1][1]).exists()
    task = database_module.get_task(updates[-1][4])
    assert task["status"] == "SUCCEEDED"
    assert '"watermark": false' in task["request_json"]
    assert task["request_json"].index('"reference_image"') < task["request_json"].index('"reference_video"')


def test_unconfirmed_generation_stays_local(tmp_path: Path, monkeypatch):
    import wan_studio.database as database_module

    monkeypatch.setattr(database_module, "DB_PATH", tmp_path / "history.db")
    database_module.init_db()
    result = list(run_generation("文生视频", [], [], [], None, None, "测试", "720P", "adaptive", False, 5, True, -1, True, False))
    assert "尚未提交" in result[-1][0]
    assert database_module.list_tasks() == []


def test_numeric_account_id_is_not_accepted_as_workspace_id():
    with pytest.raises(ValueError, match="纯数字"):
        Settings(api_key="test", workspace_id="12345678", mock_api=False).validate_real_api()
