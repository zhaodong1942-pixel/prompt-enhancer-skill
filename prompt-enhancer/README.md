# prompt-enhancer 提示词增强技能

把一条原始提示词改写成更清晰、更具体、更可能得到高质量回复的版本。

核心哲学：**只补不造** —— 只补能从原文合理推断的缺失维度，推断不出的用 `[待补充：xxx]` 占位，绝不编造事实。

## 功能

- 输入解析：规范化、语言识别（zh / en / mixed）
- 意图识别：技术 / 分析 / 创作 / 查询
- 缺口分析：逐项检测角色、目标、受众、上下文、约束、输出格式、验收标准七个维度的缺失
- 增强组装：原文 + 缺失维度的占位清单 + 改动说明

## 目录结构

```
prompt-enhancer/
├── SKILL.md                         # 技能定义与调用说明
├── scripts/
│   └── enhance.py                   # 核心模块：无副作用的纯函数接口 + CLI 入口
└── references/
    └── system-prompt.md             # 供真实 LLM 改写使用的 system prompt
```

## 快速开始

### 1. CLI 调用

```bash
python3 scripts/enhance.py "帮我写一个周报"
echo "写个登录接口，要安全" | python3 scripts/enhance.py   # 支持 stdin 管道
```

输出 JSON，退出码 `0` 成功 / `1` 失败。

### 2. import 复用（供其他 agent）

```python
import sys
sys.path.insert(0, "prompt-enhancer/scripts")
from enhance import enhance, to_dict, PRINCIPLES, GAP_DIMENSIONS

result = enhance("帮我写一个周报")   # 纯规则，无副作用
d = to_dict(result)                   # 纯 dict，可直接 json.dumps
```

### 3. 接入真实 LLM 改写

脚本默认只做纯规则改写（不调 LLM、不联网、不写文件）。若要高质量改写：

1. 读 `references/system-prompt.md`，取其 system prompt 正文
2. 用原文作 user prompt，按 JSON 约束返回 `{ enhancedPrompt, changes, language }`
3. 替换 `enhance()` 里的规则组装部分，函数签名和返回结构保持不变

## 接口说明

**入参**：`enhance(text, *, model=None, session_id=None)` —— 后两个为兼容性预留，当前实现不使用，保留以便替换为真实 LLM 实现时接口不变。

**返回** `EnhanceResult`（dataclass）：

| 字段 | 说明 |
|---|---|
| `original` | 规范化后的原文 |
| `enhanced` | 增强后的完整提示词 |
| `language` | 检测语言（zh / en / mixed） |
| `gaps` | 缺口列表（dimension / label / detected / placeholder） |
| `changes` | 逐条改动说明 |
| `ok` / `error` | 是否成功；任何异常都被捕获并返回，绝不上抛 |

## 增强原则（硬约束）

语言一致、保持意图、只补不造、明确格式、长度克制、可回退。

## 在 Codex 中使用

1. 复制到 `~/.codex/skills/prompt-enhancer/`（Codex 自动扫描加载）
2. 创建 slash command `~/.codex/commands/enhance.md`
3. 在会话中输入 `/enhance <提示词>` 即可触发改写

## License

MIT
