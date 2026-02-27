# MediCare AI Backend

Python FastAPI backend for:
- medicine side-effect analysis
- AI medical assistant chat (prescription + medicine use + diet/exercise guidance)

## Features
- Accepts medicine + symptom input for side-effect analysis.
- Provides chat guidance on medicines, health, exercise, food, and diet.
- Uses Gemini API only in backend (no direct client API calls).
- Side-effect endpoint returns:
  - `severity`
  - `possible_reasons`
  - `immediate_actions`
  - `doctor_consultation_needed`
  - `urgency`
- Both endpoints have safe fallback logic if AI call fails.

## 1) Setup
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Set values in `.env`:
- `GEMINI_API_KEY`
- optional: `GEMINI_MODEL`, `ALLOWED_ORIGINS`

## 2) Run locally
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Health check:
`GET http://localhost:8000/health`

## 3) Side-effect endpoint
`POST /api/v1/side-effects/analyze`

Example body:
```json
{
  "medicine_name": "Amoxicillin",
  "dose": "500mg",
  "taken_at": "2026-02-22T10:30:00Z",
  "symptoms": ["rash", "itching"],
  "patient_age": 28,
  "patient_gender": "female",
  "known_conditions": ["asthma"],
  "extra_notes": "Started after second dose"
}
```

## 4) Use from Flutter
Call your deployed backend URL:
`https://<your-backend-domain>/api/v1/side-effects/analyze`

## 5) Medical assistant chat endpoint
`POST /api/v1/assistant/chat`

Example body:
```json
{
  "user_message": "Please explain this prescription and what each medicine is for.",
  "prescription_image_base64": "<base64_of_image>",
  "prescription_image_mime_type": "image/jpeg",
  "history": [
    "I have mild acidity.",
    "Can I exercise daily?"
  ]
}
```

Response body:
```json
{
  "ok": true,
  "source": "gemini",
  "data": {
    "reply": "....",
    "medicine_uses": ["..."],
    "health_guidance": ["..."],
    "diet_guidance": ["..."],
    "exercise_guidance": ["..."],
    "precautions": ["..."],
    "emergency": false,
    "disclaimer": "Educational guidance only, not a diagnosis or emergency service. For severe symptoms, seek immediate medical care."
  }
}
```

## Important
This service is decision support only. It is not a diagnosis system.

