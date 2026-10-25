"""Agent 间通信的统一消息对象。

所有 Agent 之间不直接调用，而是通过 Message 传递任务、结果与反馈，
消息同时写入 WorkflowState 与事件日志，便于追踪。
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List


def timestamp() -> str:
    """统一的秒级时间戳，日志与消息共用。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class Message:
    sender: str                              # 发送方（Agent 名或 executor）
    receiver: str                            # 接收方
    type: str                                # task / result / feedback / system
    content: str                             # 消息正文（任务描述或结果摘要）
    artifacts: List[str] = field(default_factory=list)   # 关联产物 key
    meta: Dict[str, Any] = field(default_factory=dict)   # 扩展字段
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    created_at: str = field(default_factory=timestamp)

    def to_dict(self) -> Dict[str, Any]:
        """转成可 JSON 序列化的字典。"""
        return asdict(self)
