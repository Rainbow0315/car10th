from __future__ import annotations

from fastapi import APIRouter

from apps.web_api.services.llm_task_service import llm_task_service
from common.schemas.llm import (
    LlmTaskExecuteRequest,
    LlmTaskExecuteResponse,
    LlmTaskPlanRequest,
    LlmTaskPlanResponse,
    LlmToolListResponse,
)

router = APIRouter()


@router.get("/tools", response_model=LlmToolListResponse, summary="List LLM-safe robot tools")
def list_llm_tools():
    return llm_task_service.list_tools()


@router.post("/tasks/plan", response_model=LlmTaskPlanResponse, summary="Plan a robot task from natural language")
async def plan_llm_task(request: LlmTaskPlanRequest):
    return await llm_task_service.plan(request)


@router.post(
    "/tasks/{plan_id}/execute",
    response_model=LlmTaskExecuteResponse,
    summary="Execute a confirmed LLM task plan",
)
def execute_llm_task(plan_id: str, request: LlmTaskExecuteRequest):
    return llm_task_service.execute(plan_id, confirmed=request.confirmed)
