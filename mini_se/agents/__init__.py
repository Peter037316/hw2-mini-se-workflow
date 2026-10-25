"""Agent 注册表。新增 Agent 只需在此登记，无需修改执行器。"""

from __future__ import annotations

from typing import Dict

from .base import BaseAgent
from .coding_agent import CodingAgent
from .design_agent import DesignAgent
from .requirement_agent import RequirementAgent


def build_agents() -> Dict[str, BaseAgent]:
    agents = [RequirementAgent(), DesignAgent(), CodingAgent()]
    return {agent.name: agent for agent in agents}
