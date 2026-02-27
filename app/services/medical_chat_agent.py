import json
from dataclasses import dataclass

import httpx

from app.config import settings
from app.models import MedicalAssistantChatRequest, MedicalAssistantChatResult


@dataclass(frozen=True)
class MedicalChatOutput:
    result: MedicalAssistantChatResult
    source: str


class MedicalChatAgent:
    async def chat(self, payload: MedicalAssistantChatRequest) -> MedicalChatOutput:
        if not settings.gemini_api_key:
            return MedicalChatOutput(
                result=self._fallback(payload),
                source="fallback",
            )

        try:
            llm_result = await self._chat_with_gemini(payload)
            llm_result = llm_result.model_copy(
                update={
                    "image_received": bool(payload.prescription_image_base64),
                }
            )
            return MedicalChatOutput(result=llm_result, source="gemini")
        except Exception:
            return MedicalChatOutput(
                result=self._fallback(payload),
                source="fallback",
            )

    async def _chat_with_gemini(
        self, payload: MedicalAssistantChatRequest
    ) -> MedicalAssistantChatResult:
        prompt = self._build_prompt(payload)
        parts = [{"text": prompt}]
        if payload.prescription_image_base64 and payload.prescription_image_mime_type:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": payload.prescription_image_mime_type,
                        "data": payload.prescription_image_base64,
                    }
                }
            )
        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.25,
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
        return MedicalAssistantChatResult.model_validate(normalized)

    def _build_prompt(self, payload: MedicalAssistantChatRequest) -> str:
        history_block = "\n".join(f"- {entry}" for entry in payload.history) or "none"
        prescription = payload.prescription_text or "none"
        image_note = (
            "A prescription image is attached. Extract relevant medicine details from it."
            if payload.prescription_image_base64 and payload.prescription_image_mime_type
            else "No prescription image attached."
        )
        return (
            "You are an experienced medication and wellness assistant.\n"
            "Goals:\n"
            "1) Explain medicine usage from the provided prescription/context.\n"
            "2) Give practical guidance on health, medicine safety, exercise, food, and diet.\n"
            "3) Use simple patient-friendly language.\n"
            "4) If you suspect emergency risk, set emergency=true and clearly advise urgent care.\n\n"
            "Return STRICT JSON only with this schema:\n"
            "{"
            '"reply":"short paragraph answer",'
            '"medicine_uses":["..."],'
            '"health_guidance":["..."],'
            '"diet_guidance":["..."],'
            '"exercise_guidance":["..."],'
            '"precautions":["..."],'
            '"emergency":true|false'
            "}\n"
            "Rules:\n"
            "- No markdown, no extra keys.\n"
            "- Never prescribe dosage changes as a doctor replacement.\n"
            "- Keep each list concise (max 6 points).\n\n"
            f"Image context: {image_note}\n"
            f"Prescription text:\n{prescription}\n\n"
            f"Conversation history:\n{history_block}\n\n"
            f"User question:\n{payload.user_message}\n"
        )

    def _extract_text_content(self, api_response: dict) -> str:
        candidates = api_response.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini returned no candidates.")
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        if not parts:
            raise ValueError("Gemini response has no parts.")
        text = parts[0].get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Gemini response text is empty.")
        return text.strip()

    def _extract_json_dict(self, raw_text: str) -> dict:
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found in model output.")
        snippet = raw_text[start : end + 1]
        parsed = json.loads(snippet)
        if not isinstance(parsed, dict):
            raise ValueError("Parsed model output is not a JSON object.")
        return parsed

    def _normalize_result(self, data: dict) -> dict:
        return {
            "reply": str(data.get("reply", "")).strip(),
            "medicine_uses": self._listify(data.get("medicine_uses")),
            "health_guidance": self._listify(data.get("health_guidance")),
            "diet_guidance": self._listify(data.get("diet_guidance")),
            "exercise_guidance": self._listify(data.get("exercise_guidance")),
            "precautions": self._listify(data.get("precautions")),
            "image_received": False,
            "emergency": bool(data.get("emergency", False)),
        }

    def _listify(self, value: object) -> list[str]:
        if isinstance(value, list):
            cleaned = [str(entry).strip() for entry in value if str(entry).strip()]
            return cleaned[:6]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _fallback(self, payload: MedicalAssistantChatRequest) -> MedicalAssistantChatResult:
        message_lower = payload.user_message.lower()
        emergency_terms = {
            "chest pain",
            "severe breathlessness",
            "fainting",
            "seizure",
            "unconscious",
            "heavy bleeding",
        }
        emergency = any(term in message_lower for term in emergency_terms)

        reply = (
            "I can help explain medicines from your prescription and provide health guidance. "
            "Please share medicine names, schedule, and any symptoms for a more accurate answer."
        )
        if emergency:
            reply = (
                "Your message may include emergency warning signs. "
                "Please seek immediate medical care or call emergency services now."
            )

        return MedicalAssistantChatResult(
            reply=reply,
            medicine_uses=[
                "Share medicine name and purpose to get use-specific guidance.",
                "Follow doctor-prescribed timing and dose exactly.",
            ],
            health_guidance=[
                "Track symptoms with date/time and discuss persistent issues with a clinician.",
                "Do not stop essential medicines abruptly without advice.",
            ],
            diet_guidance=[
                "Stay hydrated and maintain balanced meals with protein and fiber.",
                "Avoid alcohol unless your doctor confirms safety with medicines.",
            ],
            exercise_guidance=[
                "Use moderate daily activity such as walking unless advised otherwise.",
                "Pause exercise and seek care if dizziness, chest pain, or severe weakness occurs.",
            ],
            precautions=[
                "Check drug interactions before adding OTC medicines or supplements.",
                "Report allergy symptoms such as rash, swelling, or breathing trouble urgently.",
            ],
            image_received=bool(payload.prescription_image_base64),
            emergency=emergency,
        )
