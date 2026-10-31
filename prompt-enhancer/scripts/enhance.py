#!/usr/bin/env python3
"""prompt-enhancer: 提示词增强模块的纯函数接口。

职责单一：接收原始提示词 + 可选参数，返回增强结果。不调用任何 LLM（纯规则改写），
也不读网络、不写文件、不读环境变量 —— 无全局副作用，可被任何 agent 直接 import 或 CLI 调用。

增强策略：不臆造信息，只做「规范化 + 结构化重组 + 缺失项占位」。
真实 LLM 改写请由调用方在拿到本模块的 gap 分析结果后自行完成（见 references/）。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import List, Optional


# --------------------------------------------------------------------------- #
# 常量：增强原则（可被外部读取，作为 LLM system prompt 的来源）
# --------------------------------------------------------------------------- #
PRINCIPLES: List[str] = [
    "语言一致：输出语言与输入语言完全一致，禁止自动翻译",
    "保持意图：不改变用户想做的事，只让表达更清晰具体",
    "只补不造：新增信息必须可从原文推断，推断不出就占位，绝不编造事实",
    "明确格式：显式写出期望的交付格式与结构",
    "长度克制：改写后长度控制在原文 1.5~3 倍以内",
    "可回退：增强是非破坏的，不删除原文有效信息",
]

# 缺失维度检查表：value 为空表示「需要补」，由 gap 分析填充占位
GAP_DIMENSIONS = [
    ("role", "角色/视角"),
    ("goal", "目标/交付物"),
    ("audience", "受众"),
    ("context", "上下文/背景"),
    ("constraint", "约束条件"),
    ("format", "输出格式"),
    ("criteria", "验收标准"),
]


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass
class Gap:
    dimension: str        # 维度英文 key，见 GAP_DIMENSIONS
    label: str            # 维度中文名
    detected: bool        # 原文中是否已存在该维度
    placeholder: str      # 缺失时建议的占位文案，如 "[待补充：受众]"


@dataclass
class EnhanceResult:
    original: str                          # 原文
    enhanced: str                          # 增强后的完整提示词
    language: str                          # 检测到的语言 zh/en/mixed
    gaps: List[Gap] = field(default_factory=list)
    changes: List[str] = field(default_factory=list)  # 逐条改动说明
    ok: bool = True
    error: str = ""


# --------------------------------------------------------------------------- #
# 输入解析
# --------------------------------------------------------------------------- #
_LANG_RE = {
    "zh": re.compile(r"[\u4e00-\u9fff]"),
    "en": re.compile(r"[A-Za-z]"),
}


def detect_language(text: str) -> str:
    """检测主语言：zh / en / mixed。"""
    zh = len(_LANG_RE["zh"].findall(text))
    en = len(_LANG_RE["en"].findall(text))
    if zh == 0 and en == 0:
        return "zh"
    if zh == 0:
        return "en"
    if en == 0:
        return "zh"
    return "mixed" if min(zh, en) / max(zh, en) > 0.2 else ("zh" if zh > en else "en")


def normalize(text: str) -> str:
    """规范化：去首尾空白、统一换行、压缩连续空白。"""
    text = text.strip()
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _intent(text: str) -> str:
    """轻量意图识别：创作 / 技术 / 分析 / 查询。"""
    t = text
    if re.search(r"代码|编程|函数|bug|报错|实现|脚本|接口|数据库|前端|后端|排查|debug|api|代码", t, re.I):
        return "technical"
    if re.search(r"对比|分析|评估|建议|方案|选型|优劣|review|compare", t, re.I):
        return "analysis"
    if re.search(r"写|文案|报告|邮件|文章|演讲稿|生成|创作|draft|write", t, re.I):
        return "creative"
    return "query"


# 各意图对应的缺失维度占位文案
_PLACEHOLDER = {
    "role": "[待补充：角色/视角]",
    "goal": "[待补充：目标/交付物]",
    "audience": "[待补充：受众]",
    "context": "[待补充：背景/上下文]",
    "constraint": "[待补充：约束条件（长度/语气/范围）]",
    "format": "[待补充：输出格式（如列表/表格/分段）]",
    "criteria": "[待补充：验收标准/示例]",
}

# 维度检测正则：判断原文是否已提及某维度
_DIM_HINTS = {
    "role": re.compile(r"作为|扮演|以.{0,6}(身份|角色|视角)|假设你是|you are|act as", re.I),
    "goal": re.compile(r"目标|目的|希望|要产出|得到|实现|做成|deliver|produce|achieve", re.I),
    "audience": re.compile(r"受众|读者|用户|客户|面向|写给|学生|团队|audience|reader", re.I),
    "context": re.compile(r"背景|前提|当前|已有|环境|项目|context|background", re.I),
    "constraint": re.compile(r"不要|禁止|限|不超过|字数|语气|风格|尽量|避免|安全|稳定|性能|兼容|constraint|limit|avoid", re.I),
    "format": re.compile(r"格式|列表|表格|分段|json|markdown|大纲|结构|以.{0,4}(形式|格式)|format|list|table", re.I),
    "criteria": re.compile(r"标准|合格|成功|示例|例子|比如|例如|验收|criteria|example", re.I),
}


# --------------------------------------------------------------------------- #
# 核心：缺口分析 + 增强
# --------------------------------------------------------------------------- #
def analyze_gaps(text: str) -> List[Gap]:
    """逐维度检测原文是否缺失，返回缺口列表（含占位建议）。"""
    gaps: List[Gap] = []
    for key, label in GAP_DIMENSIONS:
        detected = bool(_DIM_HINTS[key].search(text))
        gaps.append(Gap(
            dimension=key,
            label=label,
            detected=detected,
            placeholder=_PLACEHOLDER[key] if not detected else "",
        ))
    return gaps


def enhance(text: str, *, model: Optional[str] = None,
            session_id: Optional[str] = None) -> EnhanceResult:
    """纯规则增强。不调用 LLM。

    model / session_id 为兼容性预留参数（对齐 WorkBuddy daemonClient.enhancePrompt 的入参），
    本模块当前不使用，但保留以便调用方替换为真实 LLM 实现时接口不变。

    返回 EnhanceResult；任何异常均被捕获并以 ok=False + error 返回，不向上抛。
    """
    if text is None:
        return EnhanceResult("", "", "zh", [], [], False, "input text is None")
    try:
        original = normalize(text)
        if not original:
            return EnhanceResult("", "", "zh", [], [], False, "input text is empty")

        lang = detect_language(original)
        intent = _intent(original)
        gaps = analyze_gaps(original)

        # 只补缺失项，不臆造
        missing = [g for g in gaps if not g.detected]
        changes: List[str] = []

        # 组装增强版：原文 + 缺失维度占位
        parts = [original]
        if missing:
            parts.append("\n\n【补充信息】")
            for g in missing:
                parts.append(f"- {g.label}：{g.placeholder}")
                changes.append(f"补充 {g.label} 维度（占位，待用户确认）")

        enhanced = "\n".join(parts)
        changes.insert(0, f"意图识别：{intent}")
        changes.append(f"语言检测：{lang}")

        return EnhanceResult(
            original=original,
            enhanced=enhanced,
            language=lang,
            gaps=gaps,
            changes=changes,
            ok=True,
            error="",
        )
    except Exception as e:  # noqa: BLE001 —— 接口边界兜底，绝不上抛
        return EnhanceResult(
            original=text, enhanced=text, language="zh", gaps=[], changes=[],
            ok=False, error=f"enhance failed: {type(e).__name__}: {e}",
        )


# --------------------------------------------------------------------------- #
# 序列化：为 JSON 输出准备的纯数据字典（无 dataclass 对象）
# --------------------------------------------------------------------------- #
def to_dict(result: EnhanceResult) -> dict:
    d = asdict(result)
    return d


# --------------------------------------------------------------------------- #
# CLI 入口：`python enhance.py '原始提示词'` 或 stdin 管道
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    text = " ".join(argv).strip()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    if not text:
        print(json.dumps({"ok": False, "error": "no input text"}, ensure_ascii=False))
        return 1
    result = enhance(text)
    print(json.dumps(to_dict(result), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
