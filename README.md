# Windows Push-to-Talk Desktop Tool

## 功能
- 全局热键录音：按下开始、松开结束（支持 `f1-f12/esc/space/enter/tab/a-z`）。
- 录音后执行 STT -> 路由 -> LLM -> 悬浮窗显示。
- 智能路由（simple/medium/complex）+ 模型自动选择 + simple fallback 升级。
- 上下文裁剪与摘要，降低 token 成本。
- 设置热键（默认 `f10`）弹出设置窗口并保存到 `settings.json`。
- 悬浮窗支持自动淡出 + 手动关闭（`×` 按钮和 `ESC`）。

## 安装
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 配置 OPENAI_API_KEY
```bash
set OPENAI_API_KEY=your_key_here
```

## 运行
```bash
python main.py
```

## 切换模型
在 `settings.json` 修改：
- `classifier_model`
- `summary_model`
- `cheap_model`
- `balanced_model`
- `premium_model`

## 切换到 OpenAI-compatible base_url
在 `settings.json` 设置：
- `llm_provider` 为 `openai_compatible`
- `base_url` 为兼容服务地址

## 调节路由规则
编辑 `utils/text_rules.py`：
- `SIMPLE_HINTS`
- `COMPLEX_HINTS`
- `WEAK_ANSWER_HINTS`

## 热键与设置
- 录音热键：`hotkey`（默认 `f8`）
- 设置窗口热键：`settings_hotkey`（默认 `f10`）
- 两者不能相同，保存时会校验并阻止冲突。

## 测试用例示例
- “这个词是什么意思” -> simple
- “帮我把这句话翻译成日语” -> simple
- “比较这两个方案的优缺点” -> medium
- “帮我设计一个带热键录音、语音转文字、悬浮窗显示的桌面架构” -> complex
- “为什么这个程序会报错，应该如何排查” -> complex


## 热键调试模式
```bash
python main.py --debug-hotkeys
```
该模式只打印按键事件和热键匹配日志，不执行录音/STT/LLM。


## ASR 配置（faster-whisper）
在 `settings.json` 可设置：`asr_provider`, `asr_model_size`, `asr_language`, `asr_device`, `asr_compute_type`。
首次运行会下载对应 Whisper 模型（例如 `small`）。CPU 较慢可改 `tiny` 或 `base`。

- 可调 ASR 参数：`asr_vad_filter`、`asr_beam_size`、`asr_min_silence_duration_ms`、`asr_device_index`。
