from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AdapterKind(str, Enum):
    cascade = "cascade"
    realtime = "realtime"
    degraded = "degraded"


class Turn(BaseModel):
    user: str
    expected_tools: list[str] = Field(default_factory=list)
    must_include: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    id: str
    title: str
    description: str = ""
    persona: str = "default"
    turns: list[Turn]
    max_latency_ms: float = 1000
    max_questions_per_turn: int = 1
    max_sentences_per_turn: int = 3
    max_time_to_first_audio_byte_ms: float | None = None


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class TurnResult(BaseModel):
    user: str
    assistant: str
    latency_ms: float
    tool_calls: list[ToolCall] = Field(default_factory=list)
    user_audio_path: str | None = None
    assistant_audio_path: str | None = None
    assistant_audio_ms: float | None = None
    time_to_first_audio_byte_ms: float | None = None
    component_timings_ms: dict[str, float] = Field(default_factory=dict)
    session_metadata: dict[str, Any] = Field(default_factory=dict)


class TurnGrade(BaseModel):
    index: int
    score: float
    failed_rules: list[str] = Field(default_factory=list)


class Evaluation(BaseModel):
    latency_score: float
    tool_recall: float
    transcript_score: float
    rubric_score: float
    turn_grade_score: float
    overall_score: float
    turn_grades: list[TurnGrade] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class RunRequest(BaseModel):
    scenario: str = "basic_booking"
    adapter: str = "cascade"


class RunReport(BaseModel):
    id: str
    scenario_id: str
    adapter: str
    turns: list[TurnResult]
    evaluation: Evaluation
    audio_dir: str | None = None


class CompareRequest(BaseModel):
    scenario: str = "basic_booking"
    adapters: list[str] = Field(default_factory=lambda: ["cascade", "realtime"])


class CompareReport(BaseModel):
    id: str
    scenario_id: str
    runs: list[RunReport]


class SuiteReport(BaseModel):
    """Aggregate result from running one adapter over multiple scenarios."""

    id: str
    adapter: str
    runs: list[RunReport]
    scenario_count: int
    overall_score: float
    tool_recall: float
    average_latency_ms: float
    p95_latency_ms: float
