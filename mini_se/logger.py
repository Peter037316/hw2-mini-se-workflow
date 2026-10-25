"""事件日志：控制台 + JSONL 双写。

每次运行在 logs/<run_id>/ 下生成 events.jsonl，最后 Executor 再写 report.md。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .message import timestamp


class EventLogger:
    def __init__(self, log_dir: Path, run_id: str) -> None:
        self.run_dir = Path(log_dir) / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events: List[Dict[str, Any]] = []
        self._stream = (self.run_dir / "events.jsonl").open("a", encoding="utf-8")

    def event(self, kind: str, **fields: Any) -> None:
        record = {"time": timestamp(), "kind": kind, **fields}
        self.events.append(record)
        self._stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._stream.flush()
        self._print(record)

    @staticmethod
    def _print(record: Dict[str, Any]) -> None:
        """控制台保持单行，方便直接粘贴进文档/录屏。"""
        kind = record["kind"].upper()
        t = record["time"]
        if kind == "MESSAGE":
            print(
                f"[{t}] [MSG ] {record['sender']} -> {record['receiver']}"
                f" ({record['msg_type']}): {record['content']}"
            )
        elif kind == "NODE_START":
            print(f"[{t}] [RUN ] {record.get('node')} - {record.get('role', '')}")
        elif kind == "NODE_END":
            print(
                f"[{t}] [OK  ] {record.get('node')} "
                f"({record.get('elapsed', 0):.2f}s, attempt {record.get('attempt', 1)})"
            )
        elif kind == "VALIDATE":
            flag = "PASS" if record.get("ok") else "FAIL"
            print(f"[{t}] [{flag}] {record.get('node')}: {record.get('detail', '')}")
        elif kind == "RETRY":
            print(
                f"[{t}] [WARN] {record.get('node')} 第 {record.get('attempt')} 次尝试失败:"
                f" {record.get('error')}"
            )
        elif kind == "REVISION":
            print(
                f"[{t}] [LOOP] 校验未通过，回到 {record.get('goto')}"
                f"（第 {record.get('round')} 轮修订）"
            )
        elif kind == "RUN_START":
            print(f"[{t}] [====] 工作流启动: {record.get('workflow')} (run_id={record.get('run_id')})")
        elif kind == "RUN_END":
            status = record.get("status")
            print(f"[{t}] [====] 工作流结束: {status}，耗时 {record.get('elapsed', 0):.2f}s")
            print(f"[{t}] [====] 产物目录: {record.get('workspace')}")
        else:
            print(f"[{t}] [{kind}] {fields_to_text(record)}")

    def close(self) -> None:
        self._stream.close()


def fields_to_text(record: Dict[str, Any]) -> str:
    ignore = {"time", "kind"}
    return " ".join(f"{k}={v}" for k, v in record.items() if k not in ignore)
