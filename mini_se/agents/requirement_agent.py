"""需求分析 Agent：把自然语言需求整理成结构化需求规格。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from ..message import Message
from ..state import WorkflowState
from .base import AgentResult, BaseAgent

# 简单关键词表，用于识别项目类型并传递给设计/编码 Agent
PROJECT_KEYWORDS = {
    "todo": ("待办", "todo", "任务清单", "事项"),
    "calculator": ("计算器", "calculator", "四则运算"),
}


class RequirementAgent(BaseAgent):
    name = "requirement"
    role = "需求分析"

    def handle(self, state: WorkflowState, message: Message) -> AgentResult:
        title, bullets = self._parse_brief(state.brief)
        if not bullets:
            raise ValueError("需求文档为空：至少需要一条功能需求")

        kind = self._detect_kind(state.brief)
        state.shared["project_kind"] = kind

        requirements = self._render(title, bullets)
        out = state.workspace / "requirements.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(requirements, encoding="utf-8")

        return AgentResult(
            content=f"完成需求分析：{len(bullets)} 条功能需求，项目类型={kind}",
            artifacts={"requirements": out},
            meta={"feature_count": len(bullets), "project_kind": kind},
        )

    @staticmethod
    def _parse_brief(brief: str) -> Tuple[str, List[str]]:
        """提取一级标题，并按小节收集功能需求（跳过约束、非功能、范围外）。"""
        title = "未命名项目"
        lines = brief.splitlines()
        has_section = any(line.strip().startswith("## ") for line in lines)
        items: List[str] = []
        section = ""

        for raw in lines:
            line = raw.strip()
            if line.startswith("# ") and title == "未命名项目":
                title = line[2:].strip()
                continue
            if line.startswith("## "):
                section = line[3:].strip()
                continue

            is_bullet = re.match(r"^[-*]\s+\S", line)
            is_numbered = re.match(r"^\d+\.\s+\S", line)
            if not (is_bullet or is_numbered):
                continue

            # 有分节时只收功能相关小节，避免把“约束”当成功能需求
            if has_section and any(
                key in section for key in ("约束", "非功能", "范围外")
            ):
                continue
            items.append(re.sub(r"^([-*]|\d+\.)\s+", "", line))

        return title, items

    @staticmethod
    def _detect_kind(brief: str) -> str:
        lower = brief.lower()
        for kind, words in PROJECT_KEYWORDS.items():
            if any(w.lower() in lower for w in words):
                return kind
        return "todo"

    @staticmethod
    def _render(title: str, bullets: List[str]) -> str:
        rows = []
        for idx, text in enumerate(bullets, start=1):
            priority = "P0" if idx <= 3 else "P1"
            rows.append(f"| FR-{idx:02d} | {text} | {priority} |")

        criteria = "\n".join(f"- [ ] AC-{i:02d}: {text}" for i, text in enumerate(bullets, 1))
        criteria += (
            "\n- [ ] AC-99: 数据在进程退出后仍然保留（本地持久化）"
            "\n- [ ] AC-100: 非法输入给出友好提示且不崩溃"
            "\n- [ ] AC-101: 自动化测试全部通过（不少于 3 个用例）"
        )

        return f"""# 需求规格说明书：{title}

> 由 RequirementAgent 基于原始需求自动整理，供 DesignAgent / CodingAgent 使用。

## 1. 项目目标

构建一个零第三方依赖的命令行应用，功能聚焦、可离线运行、可自动化验证。

## 2. 功能需求

| 编号 | 需求描述 | 优先级 |
|------|----------|--------|
{chr(10).join(rows)}

## 3. 验收标准

{criteria}

## 4. 非功能需求

- 运行环境：Python 3.9+，仅使用标准库
- 可维护性：模块职责单一，关键函数带注释
- 可靠性：数据文件损坏时可降级为空列表，不直接崩溃
- 性能：单条命令响应时间小于 100ms

## 5. 范围外

- 图形界面、网络同步、多用户并发均不在本期范围
"""
