"""编码 Agent：按设计文档生成可运行的命令行应用与自动化测试。

采用“模板 + 需求上下文”的确定性实现：不依赖外部大模型或 API Key，
保证任何机器上都能一键复现；接口保持不变时可直接替换为 LLM 实现。
"""

from __future__ import annotations

from pathlib import Path

from ..message import Message
from ..state import WorkflowState
from .base import AgentResult, BaseAgent

APP_TEMPLATE = r'''#!/usr/bin/env python3
"""TODO CLI - 命令行待办事项应用（由 CodingAgent 自动生成）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

DEFAULT_DATA_FILE = Path(
    os.environ.get("TODO_DATA", str(Path(__file__).with_name("tasks.json")))
)


@dataclass
class Task:
    """单条待办事项。"""

    id: int
    title: str
    done: bool = False
    created_at: str = ""

    @classmethod
    def create(cls, task_id: int, title: str) -> "Task":
        return cls(
            id=task_id,
            title=title,
            done=False,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )


# ==================== 数据持久层 ====================
def load_tasks(path: Path) -> List[Task]:
    """读取 JSON；文件缺失或损坏时安全降级为空列表。"""
    path = Path(path)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    tasks: List[Task] = []
    for item in raw:
        try:
            tasks.append(Task(**item))
        except TypeError:
            continue
    return tasks


def save_tasks(path: Path, tasks: List[Task]) -> None:
    """原子化程度足够 MVP 使用：先序列化再覆盖写。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(task) for task in tasks]
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ==================== 应用服务层 ====================
def add_task(tasks: List[Task], title: str) -> Task:
    title = title.strip()
    if not title:
        raise ValueError("标题不能为空")
    task = Task.create(max((t.id for t in tasks), default=0) + 1, title)
    tasks.append(task)
    return task


def complete_task(tasks: List[Task], task_id: int) -> bool:
    for task in tasks:
        if task.id == task_id:
            task.done = True
            return True
    return False


def delete_task(tasks: List[Task], task_id: int) -> bool:
    for index, task in enumerate(tasks):
        if task.id == task_id:
            del tasks[index]
            return True
    return False


def summarize(tasks: List[Task]) -> dict:
    total = len(tasks)
    done = sum(1 for task in tasks if task.done)
    rate = round(done / total * 100, 1) if total else 0.0
    return {"total": total, "done": done, "rate": rate}


# ==================== CLI 交互层 ====================
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo", description="命令行待办事项")
    parser.add_argument("--data", default=str(DEFAULT_DATA_FILE), help="数据文件路径")
    sub = parser.add_subparsers(dest="command", required=True)

    add_parser = sub.add_parser("add", help="新增事项")
    add_parser.add_argument("title", help="事项标题")

    sub.add_parser("list", help="列出事项")

    done_parser = sub.add_parser("done", help="标记完成")
    done_parser.add_argument("task_id", type=int)

    delete_parser = sub.add_parser("delete", help="删除事项")
    delete_parser.add_argument("task_id", type=int)

    sub.add_parser("stats", help="统计信息")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.data)
    tasks = load_tasks(path)

    try:
        if args.command == "add":
            task = add_task(tasks, args.title)
            save_tasks(path, tasks)
            print(f"已添加 #{task.id}: {task.title}")
        elif args.command == "list":
            if not tasks:
                print("暂无事项。使用 add 命令添加。")
            for task in tasks:
                mark = "x" if task.done else " "
                print(f"[{mark}] #{task.id}  {task.title}  ({task.created_at})")
        elif args.command == "done":
            if not complete_task(tasks, args.task_id):
                raise ValueError(f"事项 #{args.task_id} 不存在")
            save_tasks(path, tasks)
            print(f"已完成 #{args.task_id}")
        elif args.command == "delete":
            if not delete_task(tasks, args.task_id):
                raise ValueError(f"事项 #{args.task_id} 不存在")
            save_tasks(path, tasks)
            print(f"已删除 #{args.task_id}")
        elif args.command == "stats":
            info = summarize(tasks)
            print(
                f"总数: {info['total']}  已完成: {info['done']}  完成率: {info['rate']}%"
            )
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

TEST_TEMPLATE = r'''#!/usr/bin/env python3
"""test_app.py - 待办应用自动化测试（由 CodingAgent 自动生成）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import app


class TodoAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name) / "tasks.json"
        self.tasks = []

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_add_assigns_incremental_id(self) -> None:
        first = app.add_task(self.tasks, "写作业")
        second = app.add_task(self.tasks, "复习")
        self.assertEqual(first.id, 1)
        self.assertEqual(second.id, 2)

    def test_add_rejects_empty_title(self) -> None:
        with self.assertRaises(ValueError):
            app.add_task(self.tasks, "   ")

    def test_complete_and_delete(self) -> None:
        task = app.add_task(self.tasks, "买牛奶")
        self.assertTrue(app.complete_task(self.tasks, task.id))
        self.assertTrue(task.done)
        self.assertFalse(app.complete_task(self.tasks, 999))
        self.assertTrue(app.delete_task(self.tasks, task.id))
        self.assertEqual(self.tasks, [])

    def test_persistence_roundtrip(self) -> None:
        app.add_task(self.tasks, "持久化")
        app.save_tasks(self.data, self.tasks)
        loaded = app.load_tasks(self.data)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].title, "持久化")
        self.assertEqual(loaded[0].created_at, self.tasks[0].created_at)

    def test_load_corrupted_file_returns_empty(self) -> None:
        self.data.write_text("{not-json", encoding="utf-8")
        self.assertEqual(app.load_tasks(self.data), [])

    def test_cli_add_stats_and_invalid_id(self) -> None:
        self.assertEqual(app.main(["--data", str(self.data), "add", "命令行"]), 0)
        self.assertEqual(app.main(["--data", str(self.data), "stats"]), 0)
        self.assertEqual(app.main(["--data", str(self.data), "done", "999"]), 2)


if __name__ == "__main__":
    unittest.main()
'''


class CodingAgent(BaseAgent):
    name = "coding"
    role = "编码实现"

    def handle(self, state: WorkflowState, message: Message) -> AgentResult:
        # 读取上游产物，确认设计已完成
        self.read_input(state, "requirements")
        self.read_input(state, "design")

        kind = state.shared.get("project_kind", "todo")
        if kind != "todo":
            raise ValueError(f"当前模板库暂不支持项目类型: {kind}")

        feedback = state.latest_message(receiver=self.name, msg_type="feedback")
        generated = state.workspace / "generated"
        generated.mkdir(parents=True, exist_ok=True)

        files = {
            "app.py": APP_TEMPLATE,
            "test_app.py": TEST_TEMPLATE,
            "__init__.py": "",
            "README.md": self._render_readme(state.revision, feedback.content if feedback else ""),
        }
        for filename, content in files.items():
            (generated / filename).write_text(content, encoding="utf-8")

        revision_note = f"，第 {state.revision} 轮修订" if state.revision else ""
        return AgentResult(
            content=f"生成待办应用 {len(files)} 个文件{revision_note}",
            artifacts={
                "generated_app": generated / "app.py",
                "generated_tests": generated / "test_app.py",
                "generated_readme": generated / "README.md",
            },
            meta={"revision": state.revision, "feedback": bool(feedback)},
        )

    @staticmethod
    def _render_readme(revision: int, feedback: str) -> str:
        revision_section = ""
        if revision:
            revision_section = (
                "\n## 修订记录\n\n"
                f"- 修订轮次: {revision}\n"
                f"- 校验反馈: {feedback.splitlines()[0] if feedback else '无'}\n"
            )
        return f"""# TODO CLI（自动生成）

由 Mini SE Workflow 的 CodingAgent 根据 design.md 生成，零第三方依赖。

## 使用

```bash
python app.py add "买牛奶"
python app.py list
python app.py done 1
python app.py delete 1
python app.py stats
```

默认数据文件为同目录 `tasks.json`，可用 `--data` 指定。

## 测试

```bash
python -m unittest -v test_app
```
{revision_section}"""
