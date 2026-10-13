from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import gradio as gr

from wan_studio.config import OUTPUT_DIR, SETTINGS, UPLOAD_DIR
from wan_studio.database import init_db
from wan_studio.media import normalize_files
from wan_studio.service import MODES, history_rows, prepare, restore, resume_pending_once, run_generation


CSS = """
.gradio-container {max-width: 1500px !important; background: #0b0f14 !important}
.panel {border: 1px solid #253044; border-radius: 14px; padding: 12px; background: #111722}
.hero {padding: 8px 4px 18px}.hero h1 {margin-bottom: 2px}
.status {min-height: 120px}
"""


def mode_ui(mode: str):
    frames = mode in {"首帧图生视频", "首尾帧生视频"}
    text_only = mode == "文生视频"
    return (
        gr.update(visible=not frames and not text_only), gr.update(visible=not frames and not text_only), gr.update(visible=not frames and not text_only),
        gr.update(visible=frames), gr.update(visible=mode == "首尾帧生视频"),
    )


def preview_config(*args):
    try:
        if not SETTINGS.mock_api:
            SETTINGS.validate_real_api()
        _, _, summary = prepare(*args, persist=False)
        return "```json\n" + json.dumps(summary, ensure_ascii=False, indent=2) + "\n```", gr.update(value=False)
    except Exception as exc:
        return f"❌ 配置校验失败：{exc}", gr.update(value=False)


def clear_prompt():
    return ""


def preview_images(value):
    paths = normalize_files(value)
    return [(str(path), f"图片{i} · {path.name}") for i, path in enumerate(paths, 1)], "、".join(f"图片{i}：{path.name}" for i, path in enumerate(paths, 1)) or "未上传图片"


def preview_videos(value):
    paths = normalize_files(value)
    return (str(paths[0]) if paths else None), "、".join(f"视频{i}：{path.name}" for i, path in enumerate(paths, 1)) or "未上传视频"


def preview_audios(value):
    paths = normalize_files(value)
    return (str(paths[0]) if paths else None), "、".join(f"音频{i}：{path.name}" for i, path in enumerate(paths, 1)) or "未上传音频"


def copy_prompt_script(prompt: str):
    return prompt, gr.Info("提示词已放入复制框，请使用 Ctrl+C 复制。")


def select_history(evt: gr.SelectData):
    return evt.value if evt.index[1] == 0 else None


def open_output_folder():
    os.startfile(OUTPUT_DIR)  # type: ignore[attr-defined]
    return f"已打开：{OUTPUT_DIR}"


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Wan Video Studio", theme=gr.themes.Base(primary_hue="orange", neutral_hue="slate"), css=CSS) as demo:
        selected_history = gr.State(None)
        gr.Markdown("# Wan Video Studio\n本地私人 Wan 3.0 视频生成工作台 · 默认模拟模式 · 所有请求强制无水印", elem_classes="hero")
        if not SETTINGS.mock_api:
            try:
                SETTINGS.validate_real_api()
            except ValueError as exc:
                gr.Markdown(f"### ⚠️ API 配置尚未就绪\n{exc}\n\n请修改项目目录的 `.env`，保存后重启程序。")
        with gr.Row():
            with gr.Column(scale=6, elem_classes="panel"):
                mode = gr.Dropdown(MODES, value=MODES[0], label="生成模式")
                with gr.Group(visible=False) as ref_images_group:
                    images = gr.File(file_count="multiple", file_types=["image"], label="参考图片（最多10张，按选择顺序编号）")
                    image_gallery = gr.Gallery(label="图片预览与编号", columns=5, height=180, interactive=False)
                    image_numbers = gr.Markdown("未上传图片")
                with gr.Group(visible=False) as ref_videos_group:
                    videos = gr.File(file_count="multiple", file_types=["video"], label="参考视频（最多5段）")
                    video_preview = gr.Video(label="视频预览（第1段）", interactive=False)
                    video_numbers = gr.Markdown("未上传视频")
                with gr.Group(visible=False) as ref_audios_group:
                    audios = gr.File(file_count="multiple", file_types=["audio"], label="参考音频（可选，最多5段）")
                    audio_preview = gr.Audio(label="音频预览（第1段）", interactive=False)
                    audio_numbers = gr.Markdown("未上传音频")
                with gr.Group(visible=False) as first_group:
                    first = gr.Image(type="filepath", label="首帧图片")
                with gr.Group(visible=False) as last_group:
                    last = gr.Image(type="filepath", label="尾帧图片")
                prompt = gr.Textbox(label="中文提示词", lines=9, placeholder="可直接引用：图片1、视频1、音频1……")
                with gr.Row():
                    clear_btn = gr.Button("清空提示词", size="sm")
                    copy_btn = gr.Button("复制提示词", size="sm")
                    copy_box = gr.Textbox(label="复制区", visible=False)
                with gr.Accordion("参数设置", open=True):
                    model = gr.Textbox(value="wan3.0-video", label="模型", interactive=False)
                    with gr.Row():
                        resolution = gr.Radio(["480P", "720P", "1080P"], value="1080P", label="分辨率")
                        ratio = gr.Dropdown(["adaptive", "16:9", "9:16", "1:1", "4:3", "3:4", "21:9"], value="adaptive", label="比例")
                    smart_duration = gr.Checkbox(value=True, label="智能时长（duration = -1）")
                    duration = gr.Slider(2, 30, value=5, step=1, label="固定时长（秒）")
                    with gr.Row():
                        audio = gr.Checkbox(value=True, label="生成音频")
                        prompt_extend = gr.Checkbox(value=True, label="智能提示词改写")
                    seed = gr.Number(value=-1, precision=0, label="随机种子（-1 为随机）")
                check_btn = gr.Button("1. 校验并显示生成配置", variant="secondary")
                config_preview = gr.Markdown("尚未校验配置。")
                confirmed = gr.Checkbox(label="我已核对配置，确认提交（真实模式会产生费用）")
                submit_btn = gr.Button("2. 开始生成", variant="primary")
            with gr.Column(scale=4, elem_classes="panel"):
                api_badge = "🟢 模拟 API：不会产生费用" if SETTINGS.mock_api else "🔴 真实 API：提交将产生费用"
                gr.Markdown(f"### 当前任务\n{api_badge}")
                status = gr.Textbox(value="等待提交", label="任务状态", lines=6, elem_classes="status")
                output_video = gr.Video(label="生成结果", interactive=False)
                download = gr.File(label="下载视频", interactive=False)
                open_btn = gr.Button("打开输出文件夹")
                open_status = gr.Textbox(show_label=False, interactive=False)
        gr.Markdown("## 历史生成任务")
        history = gr.Dataframe(headers=["本地ID", "创建时间", "模式", "提示词", "状态", "云端任务ID"], value=history_rows, interactive=False, wrap=True)
        with gr.Row():
            refresh_btn = gr.Button("刷新历史")
            restore_btn = gr.Button("恢复所选任务参数")

        mode.change(mode_ui, mode, [ref_images_group, ref_videos_group, ref_audios_group, first_group, last_group])
        images.change(preview_images, inputs=images, outputs=[image_gallery, image_numbers])
        videos.change(preview_videos, inputs=videos, outputs=[video_preview, video_numbers])
        audios.change(preview_audios, inputs=audios, outputs=[audio_preview, audio_numbers])
        clear_btn.click(clear_prompt, outputs=prompt)
        copy_btn.click(None, inputs=prompt, outputs=copy_box, js="(text) => { navigator.clipboard.writeText(text); return text; }")
        prepare_inputs = [mode, images, videos, audios, first, last, prompt, resolution, ratio, smart_duration, duration, audio, seed, prompt_extend]
        for field in prepare_inputs:
            field.change(lambda: False, outputs=confirmed)
        check_btn.click(preview_config, prepare_inputs, [config_preview, confirmed])
        submit_btn.click(run_generation, prepare_inputs + [confirmed], [status, output_video, download, history, selected_history])
        refresh_btn.click(history_rows, outputs=history)
        history.select(select_history, outputs=selected_history)
        restore_btn.click(restore, selected_history, [mode, images, videos, audios, first, last, prompt, resolution, ratio, smart_duration, duration, audio, seed, prompt_extend, output_video, download, status])
        open_btn.click(open_output_folder, outputs=open_status)
    return demo


if __name__ == "__main__":
    init_db()
    threading.Thread(target=resume_pending_once, daemon=True, name="wan-task-recovery").start()
    build_ui().queue(default_concurrency_limit=2).launch(server_name="127.0.0.1", server_port=7860, share=False, allowed_paths=[str(OUTPUT_DIR), str(UPLOAD_DIR)])
