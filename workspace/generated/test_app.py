#!/usr/bin/env python3
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
