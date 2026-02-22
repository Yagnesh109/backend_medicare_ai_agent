from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models import (
    ErrorResponse,
    SideEffectAnalysisRequest,
    SideEffectAnalysisResponse,
)
from app.services.ai_agent import SideEffectAgent

app = FastAPI(
    title="MediCare Side-Effect Agent API",
    version="1.0.0",
    description=(
        "Analyzes medicine side-effect reports and returns severity, likely reasons, "
        "and consultation guidance."
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

