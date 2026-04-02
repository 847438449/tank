# Windows 系统音频日语实时转写（高精度版）

基于 Python + faster-whisper 的桌面工具，目标是：在**背景音乐 + 连续长语音**场景下依然保持可用精度与稳定性。

## 核心能力

- **WASAPI loopback**：抓系统播放音频（非麦克风）。
- **混合分段策略**：短帧采集 + 静音切段 + 最大段长强制切段。
- **滑动窗口重叠识别**：针对长段，降低断句/重复。
- **两阶段识别**：
  - 快速识别（GUI 实时预览）
  - 高精度识别（最终写入 TXT / SRT）
- **GPU 优先 + 自动回退 CPU**：
  - 默认先尝试 `cuda + float16`
  - 初始化或运行时出错自动切 `cpu + int8`
  - 当前段音频会在 CPU 立即重试，尽量不丢数据

---

## 项目结构

- `audio_capture.py`：WASAPI loopback 采集 + 轻量能量 VAD
- `transcriber.py`：音频预处理、混合分段、滑窗重叠、两阶段识别、后处理、GPU/CPU回退
- `file_writer.py`：TXT 主输出 + 可选 SRT 导出
- `gui.py`：Tkinter GUI（实时预览 + 最终段落）
- `main.py`：应用编排、线程生命周期、异常处理
- `requirements.txt`

---

## 环境要求

- 操作系统：**Windows**（WASAPI loopback）
- Python：建议 3.10+

### CUDA / GPU 说明

启用 GPU 需满足：

1. Windows + NVIDIA GPU
2. CUDA 12.x
3. 与 `faster-whisper / ctranslate2` 匹配的 cuDNN

程序行为：

- 启动先尝试 GPU（`device="cuda"`, `compute_type="float16"`）
- 若失败自动回退 CPU（`device="cpu"`, `compute_type="int8"`）
- 若运行中遇到 GPU 相关错误（如 cublas/cudnn/cuda），当前音频会自动改用 CPU 重试

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

## 默认识别参数（高精度阶段）

- `model_size="medium"`（可改 `large-v3`）
- `language="ja"`
- `vad_filter=True`
- `beam_size=8`
- `best_of=5`
- `condition_on_previous_text=True`
- `temperature=0.0`

默认 `initial_prompt`：

> これは日本語の動画音声の文字起こしです。自然な日本語として出力してください。句読点を適切に補い、不要な繰り返しは減らし、固有名詞やカタカナ語をできるだけ正確に保ってください。

---

## 音频预处理（送入转写前）

- 转单声道
- 统一 16k（必要时重采样）
- RMS 音量归一化
- 轻量 band-pass（人声频段）
- 背景噪声能量抑制（轻量 noise gate）

这些逻辑已封装在 `transcriber.py` 的独立函数中，便于替换更强降噪/增强模型。

---

## 分段策略（混合）

- 采集短帧：默认 `0.4s`
- 有声则累积
- 尾部静音超过 `0.8s` 且段长超过 `2.5s` → 切段
- 即使无静音，超过 `11s` 强制切段
- 长段识别使用 `7s` 窗口 + `1s` 重叠拼接

---

## 输出格式

TXT（主输出）：

```text
[12:10:01]
今日はですね、ちょっと新しい企画について話したいと思います。

[12:10:08]
まず最初に前回の内容を振り返って、そのあと今後の予定なんですが……
```

可选 SRT：勾选 GUI 中“可选导出 SRT”。

---

## 稳定性说明

- 音频线程异常：记录日志并在 GUI 状态提示，不会直接让界面崩溃。
- 转写异常：记录并尽量继续后续段落处理。
- 停止程序：会 flush 最后一段并尽可能安全释放线程与文件句柄。
