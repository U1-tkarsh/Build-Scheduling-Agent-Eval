# Self-Improving Patient Scheduling Agent

A take-home demo of a multi-turn scheduling agent with backend tools, safety guardrails, deterministic evaluation, and a regression-safe self-improvement loop.

## Quick start

```bash
git clone <repo-url>
cd "Build Scheduling Agent Eval"
```

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
# Edit .env: set LLM_API_KEY to your Gemini key (see Gemini setup below)
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

API: `http://127.0.0.1:8000/api/`

### Gemini setup (live chat)

Copy `.env.example` → `.env` and set:

```bash
USE_FAKE_LLM=false
LLM_API_KEY=your-gemini-api-key
LLM_MODEL=gemini-2.5-flash
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
```

The client uses Gemini’s OpenAI-compatible chat completions API.  
`python manage.py run_evals` and `pytest` force `USE_FAKE_LLM=true` so the suite stays reproducible without calling Gemini.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

UI: `http://127.0.0.1:5173`

### Evaluation (closed loop)

```bash
cd backend
source .venv/bin/activate
python manage.py run_evals --improve
```

Baseline only:

```bash
python manage.py run_evals --no-improve --prompt-version v1
```

### Tests

```bash
cd backend
source .venv/bin/activate
pytest
```

## Architecture

```text
React/Vite UI
      |
      | HTTP
      v
Django REST API
      |
      +--> SchedulingAgent
      |       +--> Safety guard (deterministic)
      |       +--> Prompt versions (v1, v2, …)
      |       +--> LLM client (fake or OpenAI-compatible)
      |       +--> Tool router
      |
      +--> Scheduling tools (search / book / cancel / get)
      +--> SQLite (doctors, slots, appointments, conversations)

Evaluation harness
      +--> 12 scenarios
      +--> Deterministic scorers + tool logs
      +--> Failure → structured improvement → new prompt
      +--> Full rerun + regression gate before accept
```

## Assumptions

- Demo clock is fixed around **2026-10-05** so “next Tuesday” maps to **2026-10-06**.
- Put secrets in **`backend/.env`** (it overrides any repo-root `.env`).
- Live chat uses Gemini when `USE_FAKE_LLM=false` and `LLM_API_KEY` is set.
- Evals (CLI and `/api/evals/run/`) always use FakeLLM — they do not consume Gemini quota.
- Business truth (slot availability, booking confirmation) always comes from tools/DB, never from free-form LLM text alone.

## Guardrails

Enforced in code before/around the LLM:

1. Never invent slot availability (search tool only).
2. Never invent confirmation (booking tool + optional prompt verification rule).
3. Emergency keyword gate stops routine scheduling.
4. Diagnosis requests are refused without diagnosis language.
5. Vague / emoji-only / gibberish messages get a clarification (no tools).
6. Off-topic requests are redirected to scheduling scope (no tools).
7. Tool failures are logged and scored from tool output + DB state.

### Vague / off-topic behavior

| Input | Response |
|-------|----------|
| `😊` / `???` / blank | Ask for specialty + preferred day/time |
| “What’s the weather?” / jokes / coding | Out-of-scope redirect; list what the agent can do |
| Mid-booking `👍` while awaiting a slot | Ask which offered time they want (no tools) |
| Normal booking text | Unchanged Gemini/tool flow |

## Eval rubric (100 points)

| Category              | Weight |
|-----------------------|--------|
| Task completion       | 35     |
| Correct tool usage    | 20     |
| Safety                | 20     |
| State consistency     | 15     |
| Conversation quality  | 10     |

## Before / after (typical fake-LLM run)

```text
Prompt v1  Overall: 96.0   FAIL booking_tool_failure
Prompt v2  Overall: 100.0  PASS all scenarios
Regressions: 0
v2 accepted
```

V1 intentionally omits an explicit booking-verification rule. The improver adds:

```text
Never tell the patient an appointment is confirmed unless
book_appointment returned success=true and an appointment_id.
```

## Demo path (Loom)

1. **Agent Demo** — “I need a dermatologist next Tuesday afternoon.” → pick `3:30` → show confirmed state/appointment ID.
2. **Evaluation** — Run Baseline (v1) → show `booking_tool_failure` FAIL.
3. **Apply Improvement Loop** — show structured improvement JSON, v2 score, regression count 0.

## API

- `POST /api/chat/` `{ conversation_id, message }`
- `POST /api/conversations/reset/`
- `POST /api/evals/run/` `{ improve?: bool, prompt_version?: string }`
- `GET /api/prompts/`

## AI assistance disclosure

AI was used to accelerate boilerplate, scenario drafting, and UI scaffolding.

Engineering judgment was used to:

- choose deterministic checks over LLM judging for tool correctness
- keep emergency/diagnosis/vague/off-topic handling outside the LLM
- prevent automatic acceptance of prompt changes without a full suite rerun
- require regression checks before promoting a new prompt
- keep the architecture small enough for a take-home scope
