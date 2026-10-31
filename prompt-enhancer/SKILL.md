---
name: prompt-enhancer
description: 提示词增强工具。将用户原始提示词改写为更清晰、更具体、更可能得到高质量回复的版本。当需要优化/润色/补全一条提示词、分析提示词缺失的维度（角色/目标/受众/格式/约束等）、或把模糊诉求转成结构化指令时使用。提供可复用、无副作用的纯函数接口 enhance()，也可作为 CLI 或供其他 agent import 调用。触发场景：用户说「增强提示词」「优化这段 prompt」「帮我补全提示词」「让这条指令更清晰」等。
---

# Prompt Enhancer（提示词增强）

## 概述

把一条原始提示词改写成更清晰、更具体、更可能得到高质量回复的版本。核心是「只补不造」：
只补能从原文合理推断的缺失维度，推断不出的用 `[待补充：xxx]` 占位，绝不编造事实。

## 何时使用

- 用户要求「增强 / 优化 / 润色 / 补全」一条提示词或指令
- 需要分析一条提示词缺失了哪些维度（角色、目标、受众、上下文、约束、输出格式、验收标准）
- 要把模糊诉求（「写得好一点」「弄专业点」）转成结构化、可度量的指令

## 在 Codex 中调用（两种方式）

### 方式一：直接跑脚本（推荐，纯规则、无副作用）

```bash
# CLI 调用，输出 JSON
python3 ~/.codex/skills/prompt-enhancer/scripts/enhance.py "帮我写一个周报"

# 或 stdin 管道
echo "写个登录接口，要安全" | python3 ~/.codex/skills/prompt-enhancer/scripts/enhance.py
```

退出码 0 成功 / 1 失败，输出 JSON（含 `enhanced` / `gaps` / `changes` / `language`）。

### 方式二：在 Codex 会话中 import 复用

```python
import sys
sys.path.insert(0, "~/.codex/skills/prompt-enhancer/scripts")  # 展开为绝对路径
from enhance import enhance, to_dict, PRINCIPLES, GAP_DIMENSIONS

result = enhance("帮我写一个周报")     # 纯规则，无副作用
d = to_dict(result)                    # 纯 dict，可直接 json.dumps
```

### 方式三：让 Codex 用真实 LLM 改写（高质量）

本脚本默认只做**纯规则改写**（不调 LLM）。若要高质量改写，由 Codex 自己完成：
1. 读 `references/system-prompt.md`，取其 system prompt 正文
2. 用用户原文作 user prompt，按 JSON 约束返回 `{ enhancedPrompt, changes, language }`
3. 或直接调用 `enhance()` 拿到缺口分析结果后，用 LLM 补齐缺失维度

## 接口说明（供 agent 复用）

**入参**：`enhance(text, *, model=None, session_id=None)` —— 后两个为兼容性预留，当前实现不使用，保留以便替换为真实 LLM 实现时接口不变。

**返回** `EnhanceResult`（dataclass）：
- `original` 规范化后的原文
- `enhanced` 增强后的完整提示词
- `language` 检测语言（zh / en / mixed）
- `gaps` 缺口列表（每个含 dimension / label / detected / placeholder）
- `changes` 逐条改动说明
- `ok` / `error` 是否成功；任何异常都被捕获并以 `ok=False + error` 返回，**绝不上抛**

## 核心流程

1. **输入解析**：规范化（去空白、统一换行）、语言识别（zh/en/mixed）
2. **意图识别**：technical（技术/编码）| analysis（分析/对比）| creative（创作）| query（查询）
3. **缺口分析**：逐维度检测是否缺失（role / goal / audience / context / constraint / format / criteria），缺失则生成占位符
4. **增强组装**：原文 + 缺失维度的占位清单，附改动说明

## 增强原则（硬约束）

见 `scripts/enhance.py` 顶部的 `PRINCIPLES` 常量，核心六条：语言一致、保持意图、只补不造、明确格式、长度克制、可回退。

## 资源

- `scripts/enhance.py` —— 可复用的纯函数接口 + CLI 入口
- `references/system-prompt.md` —— 供真实 LLM 改写用的 system prompt 与参数建议
