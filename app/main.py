from fastapi import FastAPI, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from twilio.twiml.voice_response import Gather, VoiceResponse

from app.config import settings
from app.models import (
    ErrorResponse,
    MedicalAssistantChatRequest,
    MedicalAssistantChatResponse,
    SideEffectAnalysisRequest,
    SideEffectAnalysisResponse,
    VoiceReminderCallData,
    VoiceReminderCallRequest,
    VoiceReminderCallResponse,
)
from app.services.ai_agent import SideEffectAgent
from app.services.medical_chat_agent import MedicalChatAgent
from app.services.voice_call_service import VoiceCallService

app = FastAPI(
    title="MediCare Health Assistant API",
    version="1.0.0",
    description=(
        "Provides AI-assisted side-effect analysis and medication wellness chat guidance."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = SideEffectAgent()
medical_chat_agent = MedicalChatAgent()
voice_call_service = VoiceCallService()


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": "side-effect-agent"}


@app.post(
    "/api/v1/side-effects/analyze",
    response_model=SideEffectAnalysisResponse,
    responses={500: {"model": ErrorResponse}},
)
async def analyze_side_effects(
    payload: SideEffectAnalysisRequest,
) -> SideEffectAnalysisResponse:
    try:
        output = await agent.analyze(payload)
        return SideEffectAnalysisResponse(
            ok=True,
            data=output.result,
            source=output.source,  # type: ignore[arg-type]
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


@app.post(
    "/api/v1/assistant/chat",
    response_model=MedicalAssistantChatResponse,
    responses={500: {"model": ErrorResponse}},
)
async def medical_assistant_chat(
    payload: MedicalAssistantChatRequest,
) -> MedicalAssistantChatResponse:
    try:
        if payload.ai_consent is not True:
            raise HTTPException(
                status_code=400,
                detail="AI consent required for assistant processing.",
            )
        output = await medical_chat_agent.chat(payload)
        return MedicalAssistantChatResponse(
            ok=True,
            data=output.result,
            source=output.source,  # type: ignore[arg-type]
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Assistant failed: {exc}") from exc


@app.post(
    "/api/v1/voice/reminder/call",
    response_model=VoiceReminderCallResponse,
    responses={500: {"model": ErrorResponse}},
)
async def place_voice_reminder_call(
    payload: VoiceReminderCallRequest,
) -> VoiceReminderCallResponse:
    try:
        out = voice_call_service.place_reminder_call(
            to_phone=payload.to_phone,
            patient_name=payload.patient_name,
            caregiver_name=payload.caregiver_name,
            medicine_name=payload.medicine_name,
            dosage=payload.dosage,
            scheduled_time=payload.scheduled_time,
            date_key=payload.date_key,
            mode=payload.mode,
        )
        return VoiceReminderCallResponse(
            ok=True,
            data=VoiceReminderCallData(
                call_sid=(out.get("call_sid") or "").strip(),
                status=(out.get("status") or "").strip(),
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Voice call failed: {exc}") from exc


@app.post("/api/v1/voice/twiml")
async def voice_twiml(
    patient_name: str = Query(default=""),
    caregiver_name: str = Query(default=""),
    medicine_name: str = Query(default="medicine"),
    dosage: str = Query(default=""),
    scheduled_time: str = Query(default=""),
    date_key: str = Query(default=""),
    mode: str = Query(default="caregiver_patient"),
) -> Response:
    patient_display = patient_name.strip() or "patient"
    caregiver_display = caregiver_name.strip() or "caregiver"
    medicine_display = medicine_name.strip() or "medicine"
    dosage_display = dosage.strip() or "as prescribed"
    time_display = scheduled_time.strip() or "now"
    date_display = date_key.strip() or "today"

    if mode == "self_patient":
        intro = (
            f"This is an automated medicine reminder. "
            f"It is time to take {medicine_display}, {dosage_display}, at {time_display} on {date_display}."
        )
    else:
        intro = (
            f"This is an automated call set by {caregiver_display}. "
            f"Hello {patient_display}, it is time to take {medicine_display}, {dosage_display}, "
            f"at {time_display} on {date_display}."
        )

    vr = VoiceResponse()
    base = settings.public_base_url.rstrip("/")
    gather_action_url = (
        f"{base}/api/v1/voice/gather"
        f"?patient_name={patient_display}"
        f"&medicine_name={medicine_display}"
        f"&scheduled_time={time_display}"
        f"&date_key={date_display}"
    )
    gather = Gather(
        input="speech dtmf",
        timeout=60,
        speech_timeout="auto",
        action=gather_action_url,
        method="POST",
    )
    gather.say(intro, voice="alice", language="en-IN")
    gather.pause(length=1)
    gather.say(
        "Please say yes if you took your medicine. "
        "If you do not respond within one minute, this dose will be marked as missed.",
        voice="alice",
        language="en-IN",
    )
    vr.append(gather)
    vr.say(
        "No response received. This reminder is marked as missed. Take care.",
        voice="alice",
        language="en-IN",
    )
    vr.hangup()
    return Response(content=str(vr), media_type="application/xml")


@app.post("/api/v1/voice/gather")
async def voice_gather(
    patient_name: str = Query(default=""),
    medicine_name: str = Query(default=""),
    scheduled_time: str = Query(default=""),
    date_key: str = Query(default=""),
    speech_result: str = Form(default=""),
    digits: str = Form(default=""),
    call_sid: str = Form(default=""),
    to_phone: str = Form(default=""),
) -> Response:
    spoken = speech_result.strip().lower()
    pressed = digits.strip()

    taken = False
    if spoken:
        if "yes" in spoken or "haan" in spoken or "ha" == spoken:
            taken = True
    if pressed == "1":
        taken = True

    response = "taken" if taken else "missed"
    if call_sid.strip():
        voice_call_service.record_response(
            call_sid=call_sid.strip(),
            to_phone=to_phone.strip(),
            response=response,
            speech_result=speech_result.strip(),
        )

    vr = VoiceResponse()
    if taken:
        vr.say(
            "Thank you. Your response has been recorded as taken. Stay healthy.",
            voice="alice",
            language="en-IN",
        )
    else:
        vr.say(
            "No valid yes response detected. This reminder is marked as missed.",
            voice="alice",
            language="en-IN",
        )
        vr.pause(length=1)
        vr.say(
            "Please take your medicine as soon as possible or contact your caregiver.",
            voice="alice",
            language="en-IN",
        )
    vr.hangup()
    return Response(content=str(vr), media_type="application/xml")


@app.post("/api/v1/voice/status")
async def voice_status_callback(
    call_sid: str = Form(default=""),
    call_status: str = Form(default=""),
) -> PlainTextResponse:
    if call_sid.strip():
        voice_call_service.record_status(
            call_sid=call_sid.strip(),
            call_status=call_status.strip() or "unknown",
        )
    return PlainTextResponse("ok")


@app.get("/api/v1/voice/reminder/result/{call_sid}")
async def voice_call_result(call_sid: str) -> dict:
    data = voice_call_service.get_result(call_sid.strip())
    if data is None:
        raise HTTPException(status_code=404, detail="Call result not found")
    return {"ok": True, "data": data}

