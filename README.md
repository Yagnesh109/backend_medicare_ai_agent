# Side-Effect AI Agent Backend

Python FastAPI backend for medicine side-effect analysis.

## Features
- Accepts medicine + symptom input from your Flutter app.
- Uses Gemini API for analysis.
- Returns:
  - `severity`
  - `possible_reasons`
  - `immediate_actions`
  - `doctor_consultation_needed`
  - `urgency`
- Has safe fallback logic if AI call fails.

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

## 3) Analyze endpoint
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
Call your deployed URL:
`https://<your-backend-domain>/api/v1/side-effects/analyze`

## Important
This service is decision support only. It is not a diagnosis system.

