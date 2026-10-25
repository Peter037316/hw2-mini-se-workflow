"""工作流校验器（Validation Step 的实现）。

校验器与 Agent 解耦：流程定义里只写校验器名字，Executor 按名字查表调用，
因此新增校验规则不需要改动执行器。
"""

from __future__ import annotations

import py_compile
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from .state import WorkflowState


@dataclass
class ValidationResult:
    ok: bool
    detail: str
    metrics: Dict[str, Any] = field(default_factory=dict)


def python_quality(state: WorkflowState) -> ValidationResult:
    """对编码 Agent 的产物做三层检查：可编译 → 单元测试通过 → 测试数量达标。"""
    gen = state.workspace / "generated"
    py_files = sorted(gen.glob("*.py"))
    if not py_files:
        return ValidationResult(False, "未找到生成的 Python 文件")

    # ===== 第1步: 语法编译检查 =====
    for path in py_files:
        try:
            py_compile.compile(
                str(path),
                cfile=str(gen / "__pycache__" / f"{path.stem}.pyc"),
                doraise=True,
            )
        except py_compile.PyCompileError as exc:
            return ValidationResult(False, f"编译失败: {exc.msg.splitlines()[-1]}")

    # ===== 第2步: 单测数量检查（评审要求“可运行且有验证”） =====
    test_file = gen / "test_app.py"
    if not test_file.exists():
        return ValidationResult(False, "缺少自动化测试文件 test_app.py")
    test_count = test_file.read_text(encoding="utf-8").count("def test_")
    if test_count < 3:
        return ValidationResult(False, f"测试用例不足 3 个（当前 {test_count} 个）")

    # ===== 第3步: 实际执行单元测试 =====
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "-v", "test_app"],
            cwd=str(gen),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return ValidationResult(False, "单元测试超时（>60s）")

    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        tail = "\n".join(output.strip().splitlines()[-12:])
        return ValidationResult(False, f"单元测试未通过:\n{tail}", {"tests": test_count})
    if not (gen / "README.md").exists():
        return ValidationResult(False, "生成代码缺少 README.md")

    return ValidationResult(
        True,
        f"编译通过，{test_count} 个测试全部通过",
        {"tests": test_count, "files": len(py_files)},
    )


VALIDATORS = {"python_quality": python_quality}
