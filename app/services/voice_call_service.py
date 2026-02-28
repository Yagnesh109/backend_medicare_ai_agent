from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from urllib.parse import urlencode

from twilio.rest import Client

from app.config import settings


@dataclass
class VoiceCallResult:
    call_sid: str
    to: str
    status: str
    response: str
    speech_result: str
    updated_at: str


class VoiceCallService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._results: dict[str, VoiceCallResult] = {}

    @property
    def is_configured(self) -> bool:
        return (
            bool(settings.twilio_account_sid.strip())
            and bool(settings.twilio_auth_token.strip())
            and bool(settings.twilio_voice_from_number.strip())
            and bool(settings.public_base_url.strip())
        )

    def _client(self) -> Client:
        return Client(settings.twilio_account_sid, settings.twilio_auth_token)

    def _base(self) -> str:
        return settings.public_base_url.rstrip("/")

    def _twiml_url(self, query: dict[str, str]) -> str:
        return f"{self._base()}/api/v1/voice/twiml?{urlencode(query)}"

    def _status_callback_url(self) -> str:
        return f"{self._base()}/api/v1/voice/status"

    def _normalize_phone(self, raw: str) -> str:
        value = (raw or "").strip()
        if not value:
            return ""
        if value.startswith("+"):
            digits = "".join(ch for ch in value[1:] if ch.isdigit())
            return f"+{digits}" if digits else ""

        digits = "".join(ch for ch in value if ch.isdigit())
        if not digits:
            return ""
        # Default India country code for plain 10-digit local numbers.
        if len(digits) == 10:
            return f"+91{digits}"
        # If user provided 91XXXXXXXXXX without '+'.
        if len(digits) == 12 and digits.startswith("91"):
            return f"+{digits}"
        return f"+{digits}"

    def place_reminder_call(
        self,
        *,
        to_phone: str,
        patient_name: str,
        caregiver_name: str,
        medicine_name: str,
        dosage: str,
        scheduled_time: str,
        date_key: str,
        mode: str,
    ) -> dict[str, Any]:
        if not self.is_configured:
            raise RuntimeError(
                "Twilio Voice is not configured. Set PUBLIC_BASE_URL, "
                "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_VOICE_FROM_NUMBER."
            )

        query = {
            "patient_name": patient_name,
            "caregiver_name": caregiver_name,
            "medicine_name": medicine_name,
            "dosage": dosage,
            "scheduled_time": scheduled_time,
            "date_key": date_key,
            "mode": mode,
        }

        normalized_to = self._normalize_phone(to_phone)
        if not normalized_to:
            raise RuntimeError(f"Invalid destination phone: {to_phone}")

        call = self._client().calls.create(
            to=normalized_to,
            from_=settings.twilio_voice_from_number,
            url=self._twiml_url(query),
            status_callback=self._status_callback_url(),
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
            method="POST",
        )

        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._results[call.sid] = VoiceCallResult(
                call_sid=call.sid,
                to=normalized_to,
                status=str(call.status or "queued"),
                response="pending",
                speech_result="",
                updated_at=now,
            )
        return {"call_sid": call.sid, "status": str(call.status or "queued")}

    def record_response(
        self,
        *,
        call_sid: str,
        to_phone: str,
        response: str,
        speech_result: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            existing = self._results.get(call_sid)
            status = existing.status if existing else "completed"
            self._results[call_sid] = VoiceCallResult(
                call_sid=call_sid,
                to=to_phone,
                status=status,
                response=response,
                speech_result=speech_result,
                updated_at=now,
            )

    def record_status(self, *, call_sid: str, call_status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            existing = self._results.get(call_sid)
            if existing is None:
                self._results[call_sid] = VoiceCallResult(
                    call_sid=call_sid,
                    to="",
                    status=call_status,
                    response="pending",
                    speech_result="",
                    updated_at=now,
                )
                return
            self._results[call_sid] = VoiceCallResult(
                call_sid=existing.call_sid,
                to=existing.to,
                status=call_status,
                response=existing.response,
                speech_result=existing.speech_result,
                updated_at=now,
            )

    def get_result(self, call_sid: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._results.get(call_sid)
        if item is None:
            return None
        return {
            "call_sid": item.call_sid,
            "to": item.to,
            "status": item.status,
            "response": item.response,
            "speech_result": item.speech_result,
            "updated_at": item.updated_at,
        }
