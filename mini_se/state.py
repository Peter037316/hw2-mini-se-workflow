"""工作流共享状态。

State 是 Agent 之间唯一的数据交换中心：
  - artifacts: 各节点产出的文件（需求文档、设计文档、生成代码）
  - messages : 完整消息流水
  - node_status: 每个节点的运行状态与重试次数
  - shared   : 轻量运行期上下文（如识别出的项目类型）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .message import Message


class WorkflowState:
    def __init__(
        self,
        brief: str,
        run_id: str,
        workspace: Path,
        log_dir: Path,
    ) -> None:
        self.brief = brief
        self.run_id = run_id
        self.workspace = Path(workspace)
        self.log_dir = Path(log_dir)

        self.artifacts: Dict[str, Path] = {}
        self.messages: List[Message] = []
        self.node_status: Dict[str, Dict[str, Any]] = {}
        self.shared: Dict[str, Any] = {}
        self.revision = 0
        self._logger: Optional[Any] = None

    def bind_logger(self, logger: Any) -> None:
        """由 Executor 注入事件日志器。"""
        self._logger = logger

    def publish(self, message: Message) -> Message:
        """记录一条消息，并同步写事件日志。"""
        self.messages.append(message)
        if self._logger:
            self._logger.event(
                "message",
                sender=message.sender,
                receiver=message.receiver,
                msg_type=message.type,
                content=message.content.replace("\n", " ")[:120],
            )
        return message

    def latest_message(self, receiver: str, msg_type: str) -> Optional[Message]:
        """取最近一条指定接收方/类型的消息（编码 Agent 用它读取反馈）。"""
        for msg in reversed(self.messages):
            if msg.receiver == receiver and msg.type == msg_type:
                return msg
        return None

    def set_status(self, node: str, status: str, **extra: Any) -> None:
        """更新节点状态：pending / running / completed / failed / passed。"""
        info = self.node_status.setdefault(node, {"attempts": 0})
        info["status"] = status
        info.update(extra)

    def register_artifact(self, key: str, path: Path) -> None:
        """登记可被后续节点读取的产物。"""
        self.artifacts[key] = Path(path)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "brief": self.brief,
            "revision": self.revision,
            "artifacts": {k: str(v) for k, v in self.artifacts.items()},
            "node_status": self.node_status,
            "messages": [m.to_dict() for m in self.messages],
            "shared": self.shared,
        }

    def dump_json(self, path: Path) -> None:
        """落盘快照，便于回放一次运行。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
