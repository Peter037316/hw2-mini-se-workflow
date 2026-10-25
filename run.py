#!/usr/bin/env python3
"""Mini SE Workflow 入口：一条命令跑完 需求 -> 设计 -> 编码 -> 校验。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mini_se.agents import build_agents          # noqa: E402
from mini_se.executor import Executor, WorkflowError   # noqa: E402
from mini_se.logger import EventLogger          # noqa: E402
from mini_se.state import WorkflowState         # noqa: E402
from mini_se.validators import VALIDATORS       # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mini SE Workflow：需求 -> 设计 -> 编码 的最小可用 Agent 工作流"
    )
    parser.add_argument("--brief", default=str(ROOT / "examples" / "brief.md"),
                        help="原始需求 Markdown 文件")
    parser.add_argument("--spec", default=str(ROOT / "workflow.json"),
                        help="工作流定义 JSON 文件")
    parser.add_argument("--workspace", default=str(ROOT / "workspace"),
                        help="产物输出目录")
    parser.add_argument("--log-dir", default=str(ROOT / "logs"),
                        help="日志目录")
    parser.add_argument("--max-revisions", type=int, default=2,
                        help="校验失败后允许的最大修订轮数")
    return parser.parse_args()


def main() -> int:
    # Windows 控制台默认 GBK，强制 UTF-8 避免中文/符号乱码
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    args = parse_args()
    brief_path = Path(args.brief)
    spec_path = Path(args.spec)
    if not brief_path.exists():
        print(f"错误：需求文件不存在 {brief_path}", file=sys.stderr)
        return 2
    if not spec_path.exists():
        print(f"错误：流程定义不存在 {spec_path}", file=sys.stderr)
        return 2

    brief = brief_path.read_text(encoding="utf-8")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    # 清理上次产物，保证本次校验只针对最新生成结果
    for stale in ("requirements.md", "design.md"):
        (workspace / stale).unlink(missing_ok=True)
    shutil.rmtree(workspace / "generated", ignore_errors=True)

    logger = EventLogger(Path(args.log_dir), run_id)
    state = WorkflowState(brief=brief, run_id=run_id, workspace=workspace,
                          log_dir=Path(args.log_dir))
    state.bind_logger(logger)

    executor = Executor(
        spec=spec,
        agents=build_agents(),
        validators=VALIDATORS,
        state=state,
        logger=logger,
        max_revisions=args.max_revisions,
    )

    try:
        executor.run()
    except WorkflowError as exc:
        print(f"\n[失败] {exc}", file=sys.stderr)
        print(f"详细日志: {logger.run_dir}", file=sys.stderr)
        return 1
    finally:
        logger.close()

    print("\n=== 流程完成 ===")
    for name in ("requirements.md", "design.md"):
        print(f"  - {workspace / name}")
    print(f"  - {workspace / 'generated'}")
    print(f"  - 运行报告: {logger.run_dir / 'report.md'}")
    print("\n试用生成的应用：")
    print(f'  py -3 "{workspace / "generated" / "app.py"}" add "体验 Mini SE Workflow"')
    print(f'  py -3 "{workspace / "generated" / "app.py"}" list')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
