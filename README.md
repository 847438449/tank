# 视频批量日语转写工具（faster-whisper）

该项目用于扫描 `input_videos` 目录中的视频文件（`mp4/mkv/avi/mov`），自动提取音频并转写为日语文字，输出为 `txt/json/srt` 三种格式到 `output` 目录。

---

## 功能特性

- 自动扫描视频：`input_videos` 下的所有支持格式文件（含子目录）
- 通过 `ffmpeg` 自动提取单声道 16kHz WAV 音频
- 使用 `faster-whisper` 执行日语语音识别（`language="ja"` 固定）
- 每个视频输出：
  - `*.txt`：纯文本
  - `*.json`：结构化分段与元信息
  - `*.srt`：字幕文件
- 支持命令行参数：
  - `--model-size`
  - `--device`
  - `--compute-type`
- 默认优先使用 NVIDIA GPU：`--device cuda --compute-type float16`
- CUDA/GPU 异常时自动回退到 CPU（默认回退 `int8`）
- 兼容 Windows（路径与命令调用方式均可跨平台）

---

## 项目结构

```text
.
├─ input_videos/              # 放入待转写视频
├─ output/                    # 输出目录（程序自动创建）
├─ transcribe_videos.py       # 主程序
├─ requirements.txt
└─ README.md
```

---

## 环境准备

### 1) 安装 Python

推荐 Python 3.10+。

### 2) 安装 ffmpeg（必须）

程序启动会检查 `ffmpeg` 是否在 PATH 中。如果不存在会报错并退出。

- **Windows (winget)**
  ```bash
  winget install Gyan.FFmpeg
  ```
- **Windows (choco)**
  ```bash
  choco install ffmpeg
  ```

安装后执行：

```bash
ffmpeg -version
```

若能输出版本信息，说明可用。

### 3) 安装依赖

```bash
pip install -r requirements.txt
```

---

## 使用方法

### 1) 放入视频文件

将视频文件放入 `input_videos`（支持 `mp4/mkv/avi/mov`）。

### 2) 运行（默认 GPU 参数）

```bash
python transcribe_videos.py --model-size small --device cuda --compute-type float16
```

> 默认模型建议从 `small` 开始，兼顾速度与效果。

### 3) CPU 运行（手动切换）

```bash
python transcribe_videos.py --model-size small --device cpu --compute-type int8
```

### 4) 使用图形界面（Tkinter）

```bash
python gui_app.py
```

GUI 支持：

- 选择输入视频目录
- 选择输出目录
- 下拉选择模型大小 / 设备 / 计算类型
- 点击按钮开始转写
- 在滚动日志框中实时查看处理输出

---

## 命令行参数说明

- `--input-dir`：输入视频目录，默认 `input_videos`
- `--output-dir`：输出目录，默认 `output`
- `--model-size`：Whisper 模型大小，默认 `small`
- `--device`：`cuda` 或 `cpu`，默认 `cuda`
- `--compute-type`：默认 `float16`（GPU 常用），CPU 可用 `int8`/`float32`
- `--beam-size`：解码 beam size，默认 `5`

示例：

```bash
python transcribe_videos.py --model-size medium --device cuda --compute-type float16 --beam-size 5
```

---

## 输出文件格式

假设输入视频为 `input_videos/demo.mp4`，则在 `output` 下会生成：

- `demo.txt`：整段文本（按识别分段换行）
- `demo.json`：包含每段 `start/end/text`、识别语言信息等
- `demo.srt`：标准字幕格式（可直接用于播放器）

---

## GPU 使用说明（NVIDIA）

推荐命令：

```bash
python transcribe_videos.py --device cuda --compute-type float16
```

程序会先尝试按你指定的 CUDA 参数加载模型。若失败，将自动回退到 CPU，并在终端输出警告。

常见场景：

- 机器无 NVIDIA GPU
- CUDA 驱动或运行时不匹配
- PyTorch/CT2 相关依赖未正确安装

若你希望稳定执行（忽略 GPU），可直接使用 CPU 参数：

```bash
python transcribe_videos.py --device cpu --compute-type int8
```

---

## 常见报错与排查

### 1) `未找到 ffmpeg`

原因：`ffmpeg` 未安装或未加入 PATH。

排查：

1. 执行 `ffmpeg -version` 检查是否可调用
2. Windows 下确认 `ffmpeg.exe` 所在目录已加入系统环境变量 PATH
3. 重新打开终端再执行

### 2) CUDA 初始化失败 / 无法使用 GPU

现象：程序提示 `[WARN] CUDA 模式初始化失败，将自动回退到 CPU`。

排查建议：

1. 使用 `nvidia-smi` 检查驱动与 GPU 是否正常
2. 检查 CUDA 与相关依赖版本匹配
3. 先用 `--device cpu --compute-type int8` 验证程序流程无误

### 3) ffmpeg 抽取音频失败

可能原因：视频损坏、编码异常、路径权限问题。

排查：

1. 手动执行 ffmpeg 命令测试该视频
2. 检查文件名是否包含特殊字符导致路径问题
3. 检查磁盘空间和写入权限

---

## 许可与说明

本项目示例用于本地批量转写流程演示，你可按需继续扩展（例如并行处理、日志系统、说话人分离等）。
