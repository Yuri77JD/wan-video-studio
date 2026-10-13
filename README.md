# Wan Video Studio

一个面向 Windows 个人使用的本地 Wan 3.0 视频生成工作台。界面为中文，使用 Gradio；任务、请求记录和素材路径存入 SQLite。默认开启模拟 API，绝不会产生云端费用。

## 快速启动

1. 安装 Python 3.10 或更高版本（建议 3.11），安装时勾选“Add Python to PATH”。
2. 双击 `start.bat`。首次启动会创建 `.venv`、安装依赖，并从 `.env.example` 创建 `.env`。
3. 浏览器打开 `http://127.0.0.1:7860`。服务仅监听本机，不开启 Gradio 分享链接。

首次请保持 `.env` 中 `MOCK_API=true`，可完整测试确认、提交、轮询、生成本地模拟视频、预览、下载和历史恢复。

## 启用真实 API

编辑 `.env`：

```dotenv
DASHSCOPE_API_KEY=sk-你的Key
DASHSCOPE_WORKSPACE_ID=你的业务空间ID
DASHSCOPE_REGION=cn-beijing
MOCK_API=false
```

API Key、Workspace ID、地域以及 Endpoint 必须匹配。默认 Endpoint 按官方北京地域形式生成：

`https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1`

如控制台给出的地址不同，可设置 `DASHSCOPE_BASE_URL` 完整覆盖。切换为真实模式后重启程序。每次实际提交前，页面都要求先校验配置并再次勾选确认。

## 使用说明

- 文生视频不接受素材。
- 首帧/首尾帧模式只接受对应帧图片，不能与参考图片、视频或音频混用。
- 多模态、视频编辑和视频延长使用参考素材。素材按类型分别编号，上传顺序与 API 数组顺序一致：图片1、图片2；视频1、视频2；音频1、音频2。
- 图片：JPG/JPEG/PNG（不可有透明通道）/BMP/WEBP，单张不超过20MB，单边240–8000像素，比例不超过8:1。
- 视频：MP4/MOV，单段1–15秒、至少16fps、单文件不超过100MB、单边240–4096像素；所有参考视频总时长不超过15秒。
- 音频：WAV/MP3，单段1–15秒、单文件不超过15MB；总时长不超过15秒。
- 有视频输入时，输入视频总时长与设定输出时长之和不能超过30秒。
- 所有 API 请求都会显式发送 `watermark: false`。脱敏后的完整请求 JSON 保存在 `data/wan_studio.db`。
- 百炼返回的视频 URL 仅短期有效，成功后程序会自动下载到 `outputs/`。

## API 实现

真实模式先通过配置的同地域 API 根地址调用 `/uploads` 上传凭证接口，将每个本地文件上传至 DashScope 临时 OSS，得到 `oss://` URL；随后以 `X-DashScope-OssResourceResolve: enable` 和 `X-DashScope-Async: enable` 提交异步任务，并通过 `/tasks/{task_id}` 轮询结果。

实现依据：

- [万相 3.0 视频生成指南](https://help.aliyun.com/zh/model-studio/wan3-video-generation-guide)
- [万相 3.0 视频生成 API 参考](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference)
- [上传本地文件获取临时 URL](https://help.aliyun.com/zh/model-studio/get-temporary-file-url)
- [Wan 文生视频指南](https://help.aliyun.com/zh/model-studio/text-to-video-guide)

## 数据与安全

- API Key 只从 `.env` / 环境变量读取，不进入前端、SQLite 或日志。
- `.env`、`data/`、`outputs/*.mp4` 已建议保持本地，不要提交到版本库。
- 本工具不删除现有视频的水印，只在生成请求中关闭水印。

## 命令行测试

在虚拟环境中运行：

```powershell
python -m pytest -q
```

