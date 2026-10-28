# AI Pulse

AI Pulse helps a company understand how well its people use AI at work, team by team.

- **Employees** sign in, pick their organization, and take a short diagnostic. Questions adapt to their job role and seniority. One open-ended answer is scored by an LLM.
- **Each employee** gets a personal report: maturity level, risks, and next steps for their role.
- **Company admins** see a dashboard of AI maturity by department and the top risks across the company.
- Some users (consultants, group-company HR) belong to **more than one organization** and choose one after login.

This codebase was started by a previous developer who has since left. It runs, but it is unfinished, and we are not confident in all of it.

## Stack

- Backend: Python, FastAPI, SQLAlchemy (SQLite by default)
- Frontend: React (Vite)
- AI: any OpenAI-compatible chat completions endpoint, or mock mode with canned responses

## Run it locally

Backend:

```bash
cd backend
pip install -r requirements.txt
python -m app.seed          # creates demo data, password for all users: pulse123
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

Tests:

```bash
cd backend
python -m pytest
```

## Demo accounts (password `pulse123`)

| Email | Organization(s) | Role |
|---|---|---|
| asha@northwind.test | Northwind Logistics | Admin |
| meera@bluepeak.test | Bluepeak Retail | Admin |
| ravi@consult.test | Both | Employee at Northwind, admin at Bluepeak |
| priya@northwind.test | Northwind Logistics | Employee (Support) |
| dev@northwind.test | Northwind Logistics | Employee (Engineering, lead) |

## AI mode

`AI_MODE=mock` (default) returns canned model responses from `backend/data/mock_ai_responses.json`. Like a real model, they are not always well-formed.

`AI_MODE=live` calls `LLM_API_URL` with `LLM_API_KEY` and `LLM_MODEL`.

## Assessment privacy and deletion

A diagnostic counts as complete for dashboard privacy only when the selected organization membership has exactly one valid response for every question assigned to that membership's job role and seniority. Responses with duplicate or unassigned question IDs, missing/blank answers, invalid multiple-choice answers, scores outside 1–5, or invalid risk labels do not count as a completed diagnostic. Department results are omitted until five distinct users have completed a valid diagnostic. Organization risk summaries include only released departments and only flags seen for at least five distinct employees.

Employees can delete their assessment responses from the personal report using **Delete my assessment data**. `DELETE /reports/me` is authorized by the signed-in membership and deletes that membership's responses in the currently selected organization; it does not accept a user or membership ID. The client request does not clarify whether deletion should cover every organization attached to a multi-organization account. The implementation deliberately limits deletion to the selected organization pending client confirmation.
