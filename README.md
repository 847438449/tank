# 日语转写工具（faster-whisper + ffmpeg + Tkinter）

本项目用于将**单个本地音频文件**或**视频 URL（优先 YouTube）**转写为日语文本，输出 `txt/json/srt` 三种文件。

- 识别语言固定：`ja`
- 默认模型：`small`
- 默认设备：`cuda`（失败自动回退 CPU）
- GUI 使用 `tkinter`，支持进度条与实时日志

---

## 功能总览

- 两种输入模式：
  1. Local audio file（本地音频文件）
  2. URL（视频链接）
- URL 模式通过 `yt-dlp` 下载媒体后转写
- 统一后端流程复用 `transcribe_videos.py`
- 输出文件：`*.txt`、`*.json`、`*.srt`
- 进度条阶段（最小保障）：
  - 10%：校验输入
  - 25%：加载本地文件 / URL 下载阶段
  - 45%：ffmpeg 提取/转换音频
  - 70%：faster-whisper 识别
  - 90%：保存输出文件
  - 100%：完成

---

## 项目结构

```text
.
├─ gui_app.py               # Tkinter 图形界面
├─ transcribe_videos.py     # 后端转写逻辑（CLI + GUI 共用）
├─ requirements.txt
└─ README.md
```

---

## 安装

推荐 Python 3.10+。

### 1) 安装 ffmpeg（必需）

程序会检查 `ffmpeg` 是否可用，不存在会报错。

- Windows (winget):
  ```bash
  winget install Gyan.FFmpeg
  ```
- Windows (choco):
  ```bash
  choco install ffmpeg
  ```

验证：

```bash
ffmpeg -version
```

### 2) 安装 Python 依赖

```bash
pip install -r requirements.txt
```

依赖包括：
- `faster-whisper`
- `ctranslate2`
- `yt-dlp`（URL 模式必需）

---

## GUI 用法（推荐）

启动：

```bash
python gui_app.py
```

### 输入模式

1. **Local audio file**
   - 选择单个本地音频文件（`*.mp3, *.wav, *.m4a, *.flac, *.aac, *.ogg`）
2. **URL**
   - 输入视频 URL（YouTube 优先）
   - 程序会先下载媒体，再执行转写

### 其他设置

- 选择输出目录
- 选择 `model size` / `device` / `compute type`
- 点击“开始转写”
- 在日志框查看详细步骤
- 进度条显示当前阶段

---

## CLI 用法

### 本地文件模式

```bash
python transcribe_videos.py \
  --mode local \
  --input-file "C:/path/to/audio.m4a" \
  --output-dir "C:/path/to/output" \
  --model-size small \
  --device cuda \
  --compute-type float16
```

### URL 模式

```bash
python transcribe_videos.py \
  --mode url \
  --url "https://www.youtube.com/watch?v=xxxx" \
  --output-dir "C:/path/to/output" \
  --model-size small \
  --device cuda \
  --compute-type float16
```

---

## 输出说明

假设输入文件名（或下载媒体名）是 `sample_audio`，输出目录下会生成：

- `sample_audio.txt`
- `sample_audio.json`
- `sample_audio.srt`

JSON 内包含：
- `source_media`
- `language`（固定 `ja`）
- `model_info`
- 分段 `segments`

---

## GPU / CPU 说明

默认参数：

- `--device cuda`
- `--compute-type float16`

当 CUDA 初始化失败时，后端会自动回退到 CPU（`int8`）。

手动强制 CPU：

```bash
python transcribe_videos.py --mode local --input-file "a.wav" --output-dir output --device cpu --compute-type int8
```

---

## 常见报错排查

### 1) 未找到 ffmpeg

- 确认已安装并加入 PATH
- 重新打开终端后执行 `ffmpeg -version`

### 2) URL 模式提示 yt-dlp 缺失

- 安装：`pip install yt-dlp`
- 验证：`yt-dlp --version`

### 3) 无效 URL / 下载失败

- 检查 URL 是否完整（`http/https`）
- 检查网络环境
- 手动运行 `yt-dlp <url>` 查看详细错误

### 4) 本地文件格式不支持

- GUI 本地模式仅支持：`mp3/wav/m4a/flac/aac/ogg`

### 5) CUDA 无法使用

- 检查 `nvidia-smi`
- 检查驱动和依赖匹配
- 临时改用 `--device cpu --compute-type int8`

---

## 兼容性

- 代码按跨平台方式编写，兼容 Windows 路径与命令调用。
- 输出文件名做了 Windows 保留字符清理。
