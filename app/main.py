from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models import (
    ErrorResponse,
    MedicalAssistantChatRequest,
    MedicalAssistantChatResponse,
    SideEffectAnalysisRequest,
    SideEffectAnalysisResponse,
)
from app.services.ai_agent import SideEffectAgent
from app.services.medical_chat_agent import MedicalChatAgent

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
        output = await medical_chat_agent.chat(payload)
        return MedicalAssistantChatResponse(
            ok=True,
            data=output.result,
            source=output.source,  # type: ignore[arg-type]
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Assistant failed: {exc}") from exc

