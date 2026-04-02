# Windows 系统音频日语实时转写（Python + faster-whisper）

一个稳定优先的 Windows 桌面小工具：

- 使用 **WASAPI loopback** 抓取系统播放音频（不是麦克风）。
- 使用 `faster-whisper` 做离线日语转写（固定 `language="ja"`）。
- 按“自然段落”输出，而不是固定 5 秒碎片。
- 默认优先尝试 **NVIDIA GPU / CUDA**，失败自动回退 CPU。
- 输出 `txt`（主）并可选导出 `srt`。

---

## 目录结构

- `audio_capture.py`：WASAPI loopback 采集 + 短帧能量检测
- `transcriber.py`：自然段聚合 + faster-whisper 转写 + GPU 回退
- `file_writer.py`：TXT 追加写入 + 可选 SRT
- `gui.py`：Tkinter 界面
- `main.py`：应用编排与生命周期
- `requirements.txt`

---

## 环境要求

- 操作系统：**Windows**（WASAPI loopback）
- Python：建议 3.10+

### CUDA / GPU 说明

要启用 GPU（CUDA）模式，需要：

1. Windows + NVIDIA GPU
2. CUDA 12.x
3. 与 `faster-whisper` / `ctranslate2` 兼容的 cuDNN

程序启动时会：

- 先尝试 `device="cuda"` + `compute_type="float16"`
- 若不可用或初始化失败，自动回退 `device="cpu"` + `compute_type="int8"`
- 并在日志中打印实际使用模式

没有 NVIDIA GPU 也可运行（CPU 模式）。

---

## 安装

```bash
pip install -r requirements.txt
```

---

## 运行

```bash
python main.py
```

---

## 转写策略（当前默认）

- 采样率：16k
- 短帧长度：0.5 秒
- 连续静音约 1.0 秒判定段落结束
- 最大段长约 14 秒（防止无限增长）
- `beam_size=5`
- `condition_on_previous_text=True`
- `vad_filter=True`
- `language="ja"`
- 默认模型：`medium`（可切换 `small` / `large-v3`）

---

## 文本输出格式（TXT）

```text
[12:10:01]
今日はですね、ちょっと新しい企画について話したいと思います。

[12:10:08]
まず最初に前回の内容を振り返って、そのあと今後の予定なんですが……
```

---

## 稳定性说明

- 停止时会安全停止采集与转写线程。
- 停止前会尽量 flush 最后一段未落盘的转写结果。
- 后台异常会记录日志，并在 GUI 状态栏提示，避免静默失败。
