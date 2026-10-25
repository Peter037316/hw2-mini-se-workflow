"""Workflow 执行器：读取 JSON 流程定义，按顺序调度 Agent 与校验节点。

支持：
  - 顺序执行
  - 节点失败后的有限重试
  - 校验失败后的条件回退（goto）与最大修订轮数
  - 全流程消息记录、状态追踪、报告生成
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from .agents.base import AgentResult, BaseAgent
from .logger import EventLogger
from .message import Message
from .state import WorkflowState

# JSON 流程定义中的失败节点数，避免编写错误导致死循环
MAX_STEPS = 100


class WorkflowError(RuntimeError):
    """流程不可恢复错误，由入口捕获后以非 0 退出码结束。"""


class Executor:
    def __init__(
        self,
        spec: Dict[str, Any],
        agents: Dict[str, BaseAgent],
        validators: Dict[str, Any],
        state: WorkflowState,
        logger: EventLogger,
        max_revisions: int = 2,
    ) -> None:
        self.spec = spec
        self.agents = agents
        self.validators = validators
        self.state = state
        self.logger = logger
        self.max_revisions = max_revisions
        self.started = time.time()

    # ==================== 主流程 ====================
    def run(self) -> None:
        steps = self.spec.get("steps", [])
        if not steps:
            raise WorkflowError("流程定义中没有 steps")

        self.logger.event(
            "run_start",
            workflow=self.spec.get("name", "workflow"),
            run_id=self.state.run_id,
            steps=len(steps),
        )

        index = 0
        visits = 0
        loop_rounds: Dict[str, int] = {}

        try:
            while index < len(steps):
                visits += 1
                if visits > MAX_STEPS:
                    raise WorkflowError(f"流程执行步数超过 {MAX_STEPS}，疑似死循环")

                step = steps[index]
                step_type = step.get("type", "agent")

                if step_type == "agent":
                    self._run_agent_step(step)
                    index += 1
                elif step_type == "validate":
                    index = self._run_validate_step(step, index, loop_rounds, steps)
                else:
                    raise WorkflowError(f"未知节点类型: {step_type}")
        except Exception:
            # 失败也要留下报告与状态快照，方便复盘
            self._write_report(status="failed")
            raise

        self._write_report(status="success")

    # ==================== Agent 节点 ====================
    def _run_agent_step(self, step: Dict[str, Any]) -> None:
        node_id = step["id"]
        agent_name = step["agent"]
        agent = self.agents.get(agent_name)
        if agent is None:
            raise WorkflowError(f"未注册的 Agent: {agent_name}")

        task_content = self._build_task(step)
        task_msg = Message(
            sender="executor",
            receiver=agent_name,
            type="task",
            content=task_content,
            artifacts=step.get("inputs", []),
            meta={"node": node_id},
        )
        self.state.publish(task_msg)
        self.state.set_status(node_id, "running")

        retries = int(step.get("retry", 0))
        last_error = ""

        for attempt in range(1, retries + 2):
            started = time.time()
            self.logger.event(
                "node_start", node=node_id, agent=agent_name, role=agent.role, attempt=attempt
            )
            try:
                result: AgentResult = agent.handle(self.state, task_msg)
                self._register_result(node_id, agent_name, result)
                elapsed = time.time() - started
                self.state.set_status(
                    node_id, "completed", attempts=attempt, elapsed=round(elapsed, 3)
                )
                self.logger.event(
                    "node_end", node=node_id, elapsed=elapsed, attempt=attempt
                )
                return
            except Exception as exc:  # noqa: BLE001 - 统一转成流程错误，保留重试机会
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt <= retries:
                    self.logger.event("retry", node=node_id, attempt=attempt, error=last_error)
                    continue

        self.state.set_status(node_id, "failed", attempts=retries + 1, error=last_error)
        raise WorkflowError(f"节点 {node_id} 执行失败: {last_error}")

    def _register_result(self, node_id: str, agent_name: str, result: AgentResult) -> None:
        for key, path in result.artifacts.items():
            self.state.register_artifact(key, Path(path))

        self.state.publish(
            Message(
                sender=agent_name,
                receiver="executor",
                type="result",
                content=result.content,
                artifacts=list(result.artifacts.keys()),
                meta={"node": node_id, **result.meta},
            )
        )

    def _build_task(self, step: Dict[str, Any]) -> str:
        """把声明的输入拼成任务描述，Agent 依据 key 读取产物正文。"""
        inputs = step.get("inputs", [])
        labels = {"brief": "原始需求", "requirements": "需求规格", "design": "设计文档"}
        parts = []
        for key in inputs:
            label = labels.get(key, key)
            parts.append(f"- {label}({key})")
        return f"[{step.get('name', step['id'])}] 请处理输入: " + "、".join(parts)

    # ==================== 校验节点 ====================
    def _run_validate_step(
        self,
        step: Dict[str, Any],
        current_index: int,
        loop_rounds: Dict[str, int],
        steps: List[Dict[str, Any]],
    ) -> int:
        node_id = step["id"]
        validator_name = step.get("validator")
        validator = self.validators.get(validator_name)
        if validator is None:
            raise WorkflowError(f"未注册的校验器: {validator_name}")

        self.state.set_status(node_id, "running")
        started = time.time()
        self.logger.event("node_start", node=node_id, agent=validator_name, role="质量校验")
        result = validator(self.state)

        self.state.set_status(
            node_id,
            "passed" if result.ok else "failed",
            attempts=1,
            elapsed=round(time.time() - started, 3),
            detail=result.detail,
        )
        self.logger.event(
            "validate", node=node_id, ok=result.ok, detail=result.detail
        )

        if result.ok:
            return current_index + 1

        # ===== 条件分支: 校验失败 → 回到指定节点修订 =====
        on_fail = step.get("on_fail", {})
        goto = on_fail.get("goto")
        max_loops = int(on_fail.get("max_loops", self.max_revisions))
        if not goto:
            raise WorkflowError(f"校验 {node_id} 未通过且未配置失败处理: {result.detail}")

        target = next((i for i, s in enumerate(steps) if s["id"] == goto), None)
        if target is None:
            raise WorkflowError(f"校验失败处理指向不存在的节点: {goto}")

        loop_rounds[node_id] = loop_rounds.get(node_id, 0) + 1
        if loop_rounds[node_id] > max_loops:
            raise WorkflowError(
                f"校验 {node_id} 连续失败，已达最大修订轮数 {max_loops}: {result.detail}"
            )

        self.state.revision += 1
        agent_name = steps[target].get("agent", "coding")
        self.logger.event(
            "revision", goto=goto, round=loop_rounds[node_id], reason=result.detail.splitlines()[0]
        )
        self.state.publish(
            Message(
                sender="executor",
                receiver=agent_name,
                type="feedback",
                content=(
                    f"第 {loop_rounds[node_id]} 轮修订反馈：{result.detail}\n"
                    "请根据上述问题修正生成物后重新提交。"
                ),
                meta={"node": node_id, "revision": self.state.revision},
            )
        )
        return target

    # ==================== 运行报告 ====================
    def _write_report(self, status: str) -> None:
        elapsed = time.time() - self.started
        self.state.dump_json(self.logger.run_dir / "state.json")

        lines = [
            "# 运行报告",
            "",
            f"- 工作流: {self.spec.get('name', '')}",
            f"- Run ID: {self.state.run_id}",
            f"- 状态: {status}",
            f"- 总耗时: {elapsed:.2f}s",
            f"- 修订轮数: {self.state.revision}",
            "",
            "## 节点状态",
            "",
            "| 节点 | 状态 | 尝试次数 | 耗时(s) |",
            "|------|------|----------|---------|",
        ]
        for node, info in self.state.node_status.items():
            lines.append(
                f"| {node} | {info.get('status', '-')} | "
                f"{info.get('attempts', 0)} | {info.get('elapsed', '-')} |"
            )

        lines += ["", "## 产物", ""]
        for key, path in self.state.artifacts.items():
            rel = Path(path)
            try:
                rel = rel.relative_to(Path.cwd())
            except ValueError:
                pass
            lines.append(f"- {key}: `{rel}`")

        lines += ["", "## 消息流水", "", "```text"]
        for msg in self.state.messages:
            lines.append(
                f"{msg.created_at}  {msg.sender} -> {msg.receiver} "
                f"[{msg.type}] {msg.content.splitlines()[0][:80]}"
            )
        lines += ["```", ""]

        report = self.logger.run_dir / "report.md"
        report.write_text("\n".join(lines), encoding="utf-8")
        self.logger.event(
            "run_end",
            status=status,
            elapsed=elapsed,
            workspace=str(self.state.workspace),
            report=str(report),
        )
