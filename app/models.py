from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SideEffectAnalysisRequest(BaseModel):
    medicine_name: str = Field(..., min_length=1, max_length=120)
    dose: str = Field(default="", max_length=120)
    taken_at: datetime | None = None
    symptoms: list[str] = Field(default_factory=list, min_length=1, max_length=20)
    patient_age: int | None = Field(default=None, ge=0, le=120)
    patient_gender: str = Field(default="", max_length=40)
    known_conditions: list[str] = Field(default_factory=list, max_length=20)
    extra_notes: str = Field(default="", max_length=1000)

    @field_validator("symptoms")
    @classmethod
    def _clean_symptoms(cls, value: list[str]) -> list[str]:
        cleaned = [entry.strip() for entry in value if entry.strip()]
        if not cleaned:
            raise ValueError("At least one symptom is required.")
        return cleaned


class SideEffectAnalysisResult(BaseModel):
    severity: Literal["low", "medium", "high", "emergency"]
    doctor_consultation_needed: bool
    urgency: Literal[
        "self_monitor",
        "call_doctor_24h",
        "seek_urgent_care",
        "emergency_now",
    ]
    possible_reasons: list[str] = Field(default_factory=list)
    immediate_actions: list[str] = Field(default_factory=list)
    warning_signs: list[str] = Field(default_factory=list)
    recommendation: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    disclaimer: str = (
        "This is educational support, not a diagnosis. "
        "If symptoms are severe or worsening, contact a doctor immediately."
    )


class SideEffectAnalysisResponse(BaseModel):
    ok: bool = True
    data: SideEffectAnalysisResult
    source: Literal["gemini", "fallback"] = "gemini"
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    ok: bool = False
    error: str

