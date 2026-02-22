import json
from dataclasses import dataclass

import httpx

from app.config import settings
from app.models import SideEffectAnalysisRequest, SideEffectAnalysisResult


@dataclass(frozen=True)
class AgentOutput:
    result: SideEffectAnalysisResult
    source: str


class SideEffectAgent:
    _emergency_terms = {
        "chest pain",
        "shortness of breath",
        "breathlessness",
        "fainting",
        "seizure",
        "unconscious",
        "severe bleeding",
        "swelling of face",
        "swelling of tongue",
        "anaphylaxis",
    }

    _high_terms = {
        "high fever",
        "persistent vomiting",
        "bloody stool",
        "black stool",
        "confusion",
        "severe headache",
        "severe rash",
        "yellow eyes",
        "yellow skin",
    }

    async def analyze(self, payload: SideEffectAnalysisRequest) -> AgentOutput:
        if not settings.gemini_api_key:
            return AgentOutput(result=self._fallback(payload), source="fallback")

        try:
            llm_result = await self._analyze_with_gemini(payload)
            return AgentOutput(result=llm_result, source="gemini")
        except Exception:
            return AgentOutput(result=self._fallback(payload), source="fallback")

    async def _analyze_with_gemini(
        self, payload: SideEffectAnalysisRequest
    ) -> SideEffectAnalysisResult:
        prompt = self._build_prompt(payload)
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(
                settings.gemini_url,
                params={"key": settings.gemini_api_key},
                headers={"Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        text = self._extract_text_content(data)
        parsed = self._extract_json_dict(text)
        normalized = self._normalize_result(parsed)
        return SideEffectAnalysisResult.model_validate(normalized)

    def _build_prompt(self, payload: SideEffectAnalysisRequest) -> str:
        return (
            "You are a careful clinical triage assistant.\n"
            "Task: Analyze possible side-effects for the medicine and symptoms below.\n"
            "Return STRICT JSON only with keys:\n"
            "{"
            '"severity":"low|medium|high|emergency",'
            '"doctor_consultation_needed":true|false,'
            '"urgency":"self_monitor|call_doctor_24h|seek_urgent_care|emergency_now",'
            '"possible_reasons":["..."],'
            '"immediate_actions":["..."],'
            '"warning_signs":["..."],'
            '"recommendation":"...",'
            '"confidence":0.0'
            "}\n"
            "Safety rules:\n"
            "1) If life-threatening symptoms are possible, mark emergency.\n"
            "2) Be conservative. If uncertain, increase urgency.\n"
            "3) No markdown, no explanation outside JSON.\n\n"
            f"Medicine name: {payload.medicine_name}\n"
            f"Dose: {payload.dose or 'unknown'}\n"
            f"Taken at: {payload.taken_at.isoformat() if payload.taken_at else 'unknown'}\n"
            f"Symptoms: {', '.join(payload.symptoms)}\n"
            f"Age: {payload.patient_age if payload.patient_age is not None else 'unknown'}\n"
            f"Gender: {payload.patient_gender or 'unknown'}\n"
            f"Known conditions: {', '.join(payload.known_conditions) or 'none'}\n"
            f"Extra notes: {payload.extra_notes or 'none'}\n"
        )

    def _extract_text_content(self, api_response: dict) -> str:
        candidates = api_response.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini returned no candidates.")

        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        if not parts:
            raise ValueError("Gemini response has no content parts.")

        text = parts[0].get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Gemini response text is empty.")
        return text.strip()

    def _extract_json_dict(self, raw_text: str) -> dict:
        try:
            value = json.loads(raw_text)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass

        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found in Gemini output.")

        snippet = raw_text[start : end + 1]
        value = json.loads(snippet)
        if not isinstance(value, dict):
            raise ValueError("Gemini JSON output is not an object.")
        return value

    def _normalize_result(self, data: dict) -> dict:
        severity = str(data.get("severity", "medium")).lower().strip()
        urgency = str(data.get("urgency", "")).lower().strip()
        confidence_raw = data.get("confidence", 0.5)

        if severity not in {"low", "medium", "high", "emergency"}:
            severity = "medium"

        urgency_by_severity = {
            "low": "self_monitor",
            "medium": "call_doctor_24h",
            "high": "seek_urgent_care",
            "emergency": "emergency_now",
        }
        if urgency not in urgency_by_severity.values():
            urgency = urgency_by_severity[severity]

        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.5

        confidence = max(0.0, min(confidence, 1.0))
        doctor_needed = bool(data.get("doctor_consultation_needed", severity != "low"))
        if severity in {"high", "emergency"}:
            doctor_needed = True

        return {
            "severity": severity,
            "doctor_consultation_needed": doctor_needed,
            "urgency": urgency,
            "possible_reasons": self._listify(data.get("possible_reasons")),
            "immediate_actions": self._listify(data.get("immediate_actions")),
            "warning_signs": self._listify(data.get("warning_signs")),
            "recommendation": str(data.get("recommendation", "")).strip(),
            "confidence": confidence,
        }

    def _listify(self, value: object) -> list[str]:
        if isinstance(value, list):
            cleaned = [str(entry).strip() for entry in value if str(entry).strip()]
            return cleaned[:10]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _fallback(self, payload: SideEffectAnalysisRequest) -> SideEffectAnalysisResult:
        symptoms_text = " | ".join(payload.symptoms).lower()

        severity = "low"
        urgency = "self_monitor"
        doctor_needed = False

        if any(term in symptoms_text for term in self._emergency_terms):
            severity = "emergency"
            urgency = "emergency_now"
            doctor_needed = True
        elif any(term in symptoms_text for term in self._high_terms):
            severity = "high"
            urgency = "seek_urgent_care"
            doctor_needed = True
        elif len(payload.symptoms) >= 3:
            severity = "medium"
            urgency = "call_doctor_24h"
            doctor_needed = True

        recommendation_map = {
            "low": "Monitor symptoms, hydrate, and continue tracking. If symptoms persist, consult your doctor.",
            "medium": "Consult your doctor within 24 hours for guidance and possible medicine adjustment.",
            "high": "Seek urgent medical care today and avoid the next dose until advised by a clinician.",
            "emergency": "Seek emergency care immediately or call emergency services now.",
        }

        return SideEffectAnalysisResult(
            severity=severity,  # type: ignore[arg-type]
            doctor_consultation_needed=doctor_needed,
            urgency=urgency,  # type: ignore[arg-type]
            possible_reasons=[
                "Possible medicine side effect",
                "Interaction with another medicine",
                "Underlying condition worsening",
            ],
            immediate_actions=[
                "Record exact symptom start time",
                "Avoid self-medicating additional drugs",
                "Keep hydration and rest",
            ],
            warning_signs=[
                "Breathing difficulty",
                "Chest pain",
                "Severe swelling/rash",
            ],
            recommendation=recommendation_map[severity],
            confidence=0.45,
        )

