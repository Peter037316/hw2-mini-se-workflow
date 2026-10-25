"""工作流引擎测试：验证修订循环、失败重试与端到端产物。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mini_se.agents import build_agents
from mini_se.agents.base import AgentResult, BaseAgent
from mini_se.executor import Executor
from mini_se.logger import EventLogger
from mini_se.state import WorkflowState
from mini_se.validators import VALIDATORS, ValidationResult

ROOT = Path(__file__).resolve().parent.parent


class FakeAgent(BaseAgent):
    def __init__(self, name: str, key: str, fail_times: int = 0) -> None:
        super().__init__()
        self.name = name
        self.role = "测试"
        self.key = key
        self.fail_times = fail_times
        self.calls = 0

    def handle(self, state, message):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("模拟节点故障")
        out = state.workspace / f"{self.name}.md"
        out.write_text(self.name, encoding="utf-8")
        return AgentResult("ok", {self.key: out})


class FlakyValidator:
    """第一次失败、第二次通过，用于触发条件回退。"""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, state):
        self.calls += 1
        if self.calls == 1:
            return ValidationResult(False, "模拟校验失败：测试用例缺失")
        return ValidationResult(True, "通过")


def build_state(tmp: Path) -> WorkflowState:
    workspace = tmp / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return WorkflowState(
        brief="brief",
        run_id="test-run",
        workspace=workspace,
        log_dir=tmp / "logs",
    )


class ExecutorTests(unittest.TestCase):
    def test_validation_failure_triggers_revision_and_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            spec = {
                "name": "test",
                "steps": [
                    {"id": "requirements", "type": "agent", "agent": "req", "inputs": ["brief"]},
                    {"id": "design", "type": "agent", "agent": "design", "inputs": ["requirements"]},
                    {
                        "id": "validate",
                        "type": "validate",
                        "validator": "flaky",
                        "on_fail": {"goto": "design", "max_loops": 2},
                    },
                ],
            }
            state = build_state(tmp)
            logger = EventLogger(tmp / "logs", "test-run")
            state.bind_logger(logger)
            agents = {"req": FakeAgent("req", "requirements"),
                      "design": FakeAgent("design", "design")}
            executor = Executor(spec, agents, {"flaky": FlakyValidator()}, state, logger)

            try:
                executor.run()
            finally:
                logger.close()

            self.assertEqual(state.revision, 1)
            self.assertEqual(agents["design"].calls, 2)
            feedback = [m for m in state.messages if m.type == "feedback"]
            self.assertEqual(len(feedback), 1)
            self.assertEqual(feedback[0].receiver, "design")
            self.assertEqual(state.node_status["validate"]["status"], "passed")

    def test_agent_retry_recovers_from_transient_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            spec = {
                "name": "test",
                "steps": [
                    {"id": "requirements", "type": "agent", "agent": "req",
                     "inputs": ["brief"], "retry": 1},
                ],
            }
            state = build_state(tmp)
            logger = EventLogger(tmp / "logs", "test-run")
            state.bind_logger(logger)
            agent = FakeAgent("req", "requirements", fail_times=1)
            executor = Executor(spec, {"req": agent}, {}, state, logger)

            try:
                executor.run()
            finally:
                logger.close()

            self.assertEqual(agent.calls, 2)
            self.assertEqual(state.node_status["requirements"]["attempts"], 2)
            self.assertTrue((tmp / "workspace" / "req.md").exists())

    def test_end_to_end_generates_passing_project(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            spec = json.loads((ROOT / "workflow.json").read_text(encoding="utf-8"))
            state = build_state(tmp)
            state.brief = (ROOT / "examples" / "brief.md").read_text(encoding="utf-8")
            logger = EventLogger(tmp / "logs", "test-run")
            state.bind_logger(logger)
            executor = Executor(spec, build_agents(), VALIDATORS, state, logger)

            try:
                executor.run()
            finally:
                logger.close()

            self.assertEqual(state.node_status["validate"]["status"], "passed")
            self.assertTrue((tmp / "workspace" / "generated" / "app.py").exists())
            self.assertTrue((tmp / "workspace" / "design.md").exists())
            self.assertTrue((tmp / "logs" / "test-run" / "report.md").exists())


if __name__ == "__main__":
    unittest.main()
