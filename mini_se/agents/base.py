"""Agent 基类与统一返回结构。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from ..message import Message
from ..state import WorkflowState


@dataclass
class AgentResult:
    content: str                                        # 给下游的消息摘要
    artifacts: Dict[str, Path] = field(default_factory=dict)   # key -> 产物路径
    meta: Dict[str, Any] = field(default_factory=dict)  # 节点附加信息


class BaseAgent(ABC):
    name: str = ""
    role: str = ""

    def __init__(self, logger: Any = None) -> None:
        self.logger = logger

    @abstractmethod
    def handle(self, state: WorkflowState, message: Message) -> AgentResult:
        """接收任务消息，读取共享状态，返回产物与结果摘要。"""

    @staticmethod
    def read_input(state: WorkflowState, key: str) -> str:
        """按 artifact key 读取上游产物正文；brief 直接取原始需求。"""
        if key == "brief":
            return state.brief
        path = state.artifacts.get(key)
        if path is None or not Path(path).exists():
            raise FileNotFoundError(f"上游产物不存在: {key}")
        return Path(path).read_text(encoding="utf-8")
