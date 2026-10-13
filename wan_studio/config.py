from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    api_key: str = os.getenv("DASHSCOPE_API_KEY", "").strip()
    workspace_id: str = os.getenv("DASHSCOPE_WORKSPACE_ID", "").strip()
    region: str = os.getenv("DASHSCOPE_REGION", "cn-beijing").strip()
    mock_api: bool = os.getenv("MOCK_API", "true").lower() in {"1", "true", "yes", "on"}
    model: str = "wan3.0-video"
    base_url_override: str = os.getenv("DASHSCOPE_BASE_URL", "").strip()

    @property
    def base_url(self) -> str:
        if self.base_url_override:
            return self.base_url_override.rstrip("/")
        if not self.workspace_id:
            return ""
        return f"https://{self.workspace_id}.{self.region}.maas.aliyuncs.com/api/v1"

    def validate_real_api(self) -> None:
        if not self.api_key:
            raise ValueError("缺少 DASHSCOPE_API_KEY，请在 .env 中配置。")
        if not self.workspace_id and not self.base_url_override:
            raise ValueError("缺少 DASHSCOPE_WORKSPACE_ID，请确保它与 API Key、地域匹配。")
        if self.workspace_id.isdigit() and not self.base_url_override:
            raise ValueError("DASHSCOPE_WORKSPACE_ID 目前是纯数字，可能填成了阿里云账号 ID。请从百炼“业务空间管理”复制业务空间 ID 或 API Host；以控制台显示的值为准。")
        if not self.base_url:
            raise ValueError("无法确定 API Endpoint。")


SETTINGS = Settings()
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = ROOT / "outputs"
DB_PATH = DATA_DIR / "wan_studio.db"
for directory in (DATA_DIR, UPLOAD_DIR, OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)
