# Windows Push-to-Talk Desktop Tool (Phase 2)

## 功能概览
- 全局热键按下录音、松开结束。
- 录音转文字（`speech_to_text.py`，当前为可替换占位实现）。
- 智能路由：`simple / medium / complex`（规则 + 轻量模型判定）。
- 根据复杂度自动选模型，支持 simple 请求失败自动升级（fallback）。
- 上下文管理：截断 + 历史摘要，避免上下文无限增长。
- 悬浮窗在鼠标附近显示回复，自动渐隐。
- LLM 抽象层：默认 OpenAI Responses API，预留 OpenAI-compatible provider。

## 项目结构
```text
project_root/
├─ main.py
├─ config.py
├─ settings.json
├─ hotkey_listener.py
├─ audio_recorder.py
├─ speech_to_text.py
├─ overlay_window.py
├─ prompt_builder.py
├─ router.py
├─ context_manager.py
├─ utils/
│  ├─ logger.py
│  ├─ text_rules.py
│  └─ helpers.py
├─ llm/
│  ├─ __init__.py
│  ├─ base.py
│  ├─ factory.py
│  ├─ openai_provider.py
│  └─ compatible_provider.py
└─ tests/
   ├─ test_router.py
   ├─ test_context_manager.py
   └─ test_fallback.py
```

## 安装依赖
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 配置 API Key
推荐使用环境变量：
```bash
set OPENAI_API_KEY=your_key_here
```

也可在 `settings.json` 填 `api_key`（不推荐提交到仓库）。

## 运行
```bash
python main.py
```

## 如何切换模型
在 `settings.json` 修改：
- `cheap_model`
- `balanced_model`
- `premium_model`
- `classifier_model`
- `summary_model`

## 如何切换 OpenAI-compatible base_url
在 `settings.json` 设置：
- `llm_provider`: `openai` 或 `openai_compatible`
- `base_url`: 你的兼容服务地址

## 如何调节 simple / medium / complex 规则
- 规则关键词在 `utils/text_rules.py`：`SIMPLE_HINTS`、`COMPLEX_HINTS`
- 路由主逻辑在 `router.py`：
  - `quick_rule_classify`
  - `ai_classify`
  - `classify_complexity`

## 示例测试输入
- “这个词是什么意思” -> simple
- “帮我把这句话翻译成日语” -> simple
- “比较这两个方案的优缺点” -> medium（通常走 AI 分类）
- “帮我设计一个带热键录音、语音转文字、悬浮窗显示的桌面架构” -> complex
- “为什么这个程序会报错，应该如何排查” -> complex

## 兼容性说明
- 已尽量保留现有模块（录音、热键、悬浮窗）不重写，仅在主流程中新增路由/上下文/抽象层接入。
- `speech_to_text.py` 当前为占位实现，后续可直接替换 `PlaceholderSTTEngine`。
- `llm/compatible_provider.py` 为占位扩展点（TODO）。
