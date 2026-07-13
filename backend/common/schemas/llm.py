from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


LlmToolName = Literal[
    "fleet.summary",
    "fleet.readiness",
    "fleet.safety_stop",
    "fleet.plate_verify",
    "fleet.escort_return",
]


class LlmToolSpec(BaseModel):
    name: LlmToolName
    title: str
    description: str
    required_arguments: list[str] = Field(default_factory=list)
    safety_level: Literal["read_only", "safe_command", "motion_command"]
    requires_confirmation: bool = True


class LlmRobotContext(BaseModel):
    robot_code: str
    status: str
    mode: str
    ready_to_command: bool
    reason: Optional[str] = None


class LlmTaskPlanStep(BaseModel):
    step_id: str
    tool: LlmToolName
    title: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    safety_level: Literal["read_only", "safe_command", "motion_command"]
    requires_confirmation: bool = True
    status: Literal["planned", "executed", "failed", "skipped"] = "planned"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class LlmTaskPlanRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    robot_codes: list[str] = Field(default_factory=lambda: ["robot_001"], max_length=20)
    allow_llm: bool = True
    auto_execute: bool = False


class LlmTaskPlanResponse(BaseModel):
    plan_id: str
    assistant_message: str
    source: Literal["llm", "rule_fallback"]
    created_at: datetime
    requires_confirmation: bool
    safety_notes: list[str] = Field(default_factory=list)
    robot_context: list[LlmRobotContext] = Field(default_factory=list)
    steps: list[LlmTaskPlanStep] = Field(default_factory=list)


class LlmTaskExecuteRequest(BaseModel):
    confirmed: bool = False


class LlmTaskExecuteResponse(BaseModel):
    plan_id: str
    executed_at: datetime
    steps: list[LlmTaskPlanStep]
    safety_notes: list[str] = Field(default_factory=list)


class LlmToolListResponse(BaseModel):
    tools: list[LlmToolSpec]
