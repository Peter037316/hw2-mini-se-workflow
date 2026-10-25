#!/usr/bin/env python3
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
