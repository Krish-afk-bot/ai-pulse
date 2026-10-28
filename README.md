# AI Pulse

AI Pulse helps a company understand how well its people use AI at work, team by team, without exposing individuals.

- **Employees** sign in, pick their organization, and take a short diagnostic. The question set adapts to their job role and seniority. One open-ended answer is scored by an LLM.
- **Each employee** gets a personal report (maturity level, risks, role-level next steps) plus an evidence-backed improvement plan derived from their own answers.
- **Company admins** see a dashboard of AI maturity by department and the top risks across the company, with small groups suppressed.
- Some users (consultants, group-company HR) belong to **more than one organization** and choose one after login.

This codebase was started by a previous developer who has since left. It runs and is covered by tests, but some parts (noted under [Known limitations](#known-limitations-and-risks)) remain unfinished.

---

## The client request and how it was implemented

The HR team at Northwind Logistics asked for two changes before rollout (see [CLIENT_REQUEST.md](CLIENT_REQUEST.md)):

> 1. **No small groups on the dashboard.** If a department has fewer than 5 people who completed the diagnostic, leadership must not see that department's scores or risks on their own.
> 2. **Right to delete.** Any employee must be able to delete all their answers and their report themselves, and it must disappear from every dashboard immediately.

Both were implemented in the dashboard and reports routes (details below). The client request does not clarify whether "delete" should cover every organization attached to a multi-organization account; the implementation deliberately limits deletion to the currently selected organization, pending client confirmation.

---

## Stages implemented

### Stage 2 — Cross-organization dashboard authorization

`GET /dashboard?org_id=<id>` in [dashboard.py](backend/app/routes/dashboard.py) is guarded by the signed-in membership:

- Non-admins get `403 "Admins only"`.
- An admin requesting an organization other than the one in their token gets `403 "Not authorized to access this organization"`.

The token carries `org` (set by `POST /auth/select-org`), so an admin of one tenant cannot read another tenant's dashboard. Regression coverage: `test_admin_cannot_see_other_org`, `test_employee_cannot_access_admin_dashboard`, `test_dashboard_cross_tenant_access_still_denied`.

### Stage 3 — Five-employee privacy threshold and employee deletion

Privacy rule, enforced in [dashboard.py](backend/app/routes/dashboard.py):

- A department is only returned when **at least five distinct users** in it have a complete, valid diagnostic.
- While a department is below the threshold, **no department-level metadata or metrics are returned at all** (not just the score) — the department is skipped entirely.
- Organization risk summaries (`top_risks`) are computed **only from released departments** and only include a flag seen for **at least five distinct employees**.

Validity is decided by `completed_responses` in [assessment.py](backend/app/services/assessment.py): a diagnostic counts only when the selected membership has **exactly one valid response for every question assigned to that membership's role and seniority**. Duplicate or unassigned question IDs, missing/blank answers, invalid multiple-choice answers, scores outside 1–5, non-finite scores, or invalid risk labels do **not** count. This is also how incomplete/duplicate submissions are kept from inflating department counts.

Deletion:

- `DELETE /reports/me` in [reports.py](backend/app/routes/reports.py) is authorized by the signed-in membership, requires `role == "employee"` (admins get `403`), and deletes that membership's responses **in the currently selected organization only**.
- The endpoint accepts **no user or membership ID**, so a caller cannot delete another person's data even if they supply a `user_id` query parameter.
- Because the dashboard re-reads `Response` rows on every request, deletion is reflected in dashboards immediately.

Regression coverage: `test_zero_completed_employees_are_suppressed`, `test_one_completed_employee_is_suppressed`, `test_four_completed_employees_are_suppressed`, `test_five_distinct_completed_employees_make_department_eligible`, `test_incomplete_and_duplicate_answers_do_not_count_as_completed`, `test_incomplete_department_does_not_leak_risk_when_another_department_is_eligible`, `test_employee_deletes_only_selected_organizations_responses_and_can_repeat`, `test_employee_deletion_removes_completed_dashboard_contribution`, `test_admin_cannot_delete_assessment_data`.

### Stage 4 — Seniority question-filtering fix

`questions_for(job_role, seniority)` in [questions.py](backend/app/services/questions.py) filters the question bank by role **and** by a seniority rank:

```
SENIORITY_RANK = {"junior": 0, "mid": 1, "senior": 2, "lead": 3}
```

A question is included only when its `min_seniority` rank is less than or equal to the member's rank, and when its `roles` list is `["all"]` or contains the member's `job_role`. This keeps role-specific questions gated by seniority (e.g. a junior engineer does not receive `eng-review` or `eng-arch`). Regression coverage: `test_junior_engineer_does_not_get_senior_questions`, `test_mid_engineer_gets_mid_questions_but_not_senior_questions`, `test_senior_engineer_gets_senior_questions`, `test_senior_support_gets_escalation_question`, `test_lead_manager_gets_policy_questions` in [test_questions.py](backend/tests/test_questions.py).

### Stage 5 — Employee assessment evidence and improvement plan

`GET /reports/me/improvement` returns, for the authenticated membership only:

- **`areas`** — one entry per assigned question: the question text, whether it is core (`roles: ["all"]`) or role-specific, the employee's saved answer and score, the stored scoring rationale when available, and any risk flags.
- **`gaps`** — assessment areas scoring below the improvement threshold (4/5).
- **`recommendations`** — two or three concrete next actions, each with a `source`, the saved `evidence`, and a short `explanation`.

Grounding rules (see [improvement.py](backend/app/services/improvement.py)):

- The plan is built **only** from the authenticated membership's own current responses plus the existing question bank. There is no user or membership input, so another employee's plan cannot be requested.
- Scoring is **not** re-implemented: it reuses stored scores, `completed_responses` for validity, `maturity_level` for the overall band, and the report's `NEXT_STEPS` role guidance (moved into the service so it is shared, not duplicated).
- Recommendations are derived deterministically: risk-flag areas first, then the lowest-scoring areas. An MCQ recommendation quotes the question's own top (`points=5`) option; a flagged open answer produces a follow-up tied to that flag; otherwise the plan falls back to role guidance.
- Saved assessment evidence (`answer`, `score`, `rationale`, `flags`) is clearly separated from generated text (`action`, `explanation`) and a top-level `note` states which is which.
- Missing/unsupported data yields an explicit state instead of fabrication: MCQs report `rationale_available: false` with a note that no written rationale is stored, and the plan returns `status` of `empty` (no saved answers) or `incomplete` (partial/invalid assessment) with no recommendations.

The report UI ([Report.jsx](frontend/src/pages/Report.jsx)) renders accessible evidence, improvement-opportunity, and next-action sections (semantic headings/lists, `role="status"` / `role="alert"`). Regression coverage: [test_improvement_plan.py](backend/tests/test_improvement_plan.py).

---

## Architecture

### Backend (FastAPI + SQLAlchemy)

| File | Responsibility |
|---|---|
| [main.py](backend/app/main.py) | App factory, CORS (`allow_origins=["*"]`), router wiring, `/health`, creates tables on startup |
| [config.py](backend/app/config.py) | Tiny `.env` loader and settings: `SECRET_KEY`, `DATABASE_URL`, `AI_MODE`, `LLM_*`, `TOKEN_HOURS` |
| [db.py](backend/app/db.py) | SQLite engine (`./aipulse.db`) and session factory |
| [models.py](backend/app/models.py) | `Organization`, `Department`, `User`, `Membership`, `Response` |
| [auth.py](backend/app/auth.py) | SHA-256 password hashing, HS256 JWT, `current_user` / `current_membership` dependencies |
| [utils.py](backend/app/utils.py) | `maturity_level` banding used by the personal report |
| [seed.py](backend/app/seed.py) | Demo orgs, users, memberships and a few answers |
| [routes/auth_routes.py](backend/app/routes/auth_routes.py) | `POST /auth/login`, `POST /auth/select-org` |
| [routes/diagnostic.py](backend/app/routes/diagnostic.py) | `GET /diagnostic/questions` (points stripped), `POST /diagnostic/submit` |
| [routes/reports.py](backend/app/routes/reports.py) | `GET /reports/me`, `GET /reports/me/improvement`, `DELETE /reports/me` |
| [routes/dashboard.py](backend/app/routes/dashboard.py) | `GET /dashboard?org_id=` (admin only, privacy-gated) |
| [services/questions.py](backend/app/services/questions.py) | Loads `data/questions.json`; role + seniority filtering |
| [services/scoring.py](backend/app/services/scoring.py) | `score_open_answer` (LLM JSON → score/reason/flags) |
| [services/llm.py](backend/app/services/llm.py) | Mock or live OpenAI-compatible scoring; rubric prompt and allowed flags |
| [services/assessment.py](backend/app/services/assessment.py) | `completed_responses` validity, `ALLOWED_RISK_FLAGS` |
| [services/improvement.py](backend/app/services/improvement.py) | Stage 5 plan builder, shared `NEXT_STEPS` |
| `data/questions.json` | Question bank (MCQ + open), role/seniority metadata, option points |
| `data/mock_ai_responses.json` | Canned LLM outputs used in mock mode |

Key endpoints:

- `POST /auth/login` → token + list of organizations/roles.
- `POST /auth/select-org` → token scoped to an organization.
- `GET /diagnostic/questions`, `POST /diagnostic/submit`.
- `GET /reports/me`, `GET /reports/me/improvement`, `DELETE /reports/me`.
- `GET /dashboard?org_id=` (admin only).

### Frontend (React + Vite)

Single-page app driven by steps in [App.jsx](frontend/src/App.jsx): **login → organization picker → (employee) diagnostic → report** or **(admin) dashboard**.

| File | Responsibility |
|---|---|
| [api.js](frontend/src/api.js) | `fetch` wrapper; token in `localStorage`; base URL from `VITE_API_URL` or `http://localhost:8000` |
| [pages/Login.jsx](frontend/src/pages/Login.jsx) | Sign-in form |
| [pages/OrgPicker.jsx](frontend/src/pages/OrgPicker.jsx) | Organization selection for multi-org users |
| [pages/Diagnostic.jsx](frontend/src/pages/Diagnostic.jsx) | Renders assigned questions, submits answers |
| [pages/Report.jsx](frontend/src/pages/Report.jsx) | Personal report, Stage 5 evidence/plan sections, delete button |
| [pages/Dashboard.jsx](frontend/src/pages/Dashboard.jsx) | Admin dashboard (**placeholder**, prints raw JSON) |

---

## Getting started

Prerequisites:

- Python 3.11+ (the Dockerfile pins 3.12)
- Node.js 18+ and npm

Environment configuration (optional):

- Configuration is read from environment variables, with defaults in [config.py](backend/app/config.py).
- A `backend/.env` file is loaded if present, but it is **not required** and **must not be committed**. Set at least `SECRET_KEY` for anything beyond local play.
- Relevant variables: `SECRET_KEY`, `DATABASE_URL` (default `sqlite:///./aipulse.db`), `AI_MODE` (`mock` or `live`), `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL`.

Backend:

```bash
cd backend
pip install -r requirements.txt
python -m app.seed          # creates demo data; password for all seeded users: pulse123
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
npm run build               # production build into dist/
```

Tests (run from `backend/`; they use `test.db` and `AI_MODE=mock`):

```bash
python -m pytest                              # full suite
python -m pytest tests/test_improvement_plan.py
python -m pytest tests/test_api.py tests/test_privacy_deletion.py
```

> Note: the app runs on a short default `SECRET_KEY`, which makes `pyjwt` emit `InsecureKeyLengthWarning`. Set a ≥32-byte `SECRET_KEY` for anything other than local development.

---

## Development accounts and seed data

`python -m app.seed` **drops and recreates** all tables, then creates two organizations (Northwind Logistics, Bluepeak Retail), departments, memberships and a handful of answers. Password for every seeded account is `pulse123`. **Never use these accounts or the seeded secret outside local development.**

| Email | Organization(s) | Role |
|---|---|---|
| asha@northwind.test | Northwind Logistics | Admin |
| meera@bluepeak.test | Bluepeak Retail | Admin |
| ravi@consult.test | Northwind Logistics + Bluepeak Retail | Employee at Northwind, admin at Bluepeak |
| priya@northwind.test | Northwind Logistics | Employee (Support, junior) |
| vikram@northwind.test | Northwind Logistics | Employee (Sales, senior) |
| dev@northwind.test | Northwind Logistics | Employee (Engineering, lead) |

Seeded answers are intentionally **partial** (e.g. Priya has two answers), so most departments start below the five-person threshold and are suppressed on the dashboard until you complete more diagnostics. The Stage 5 endpoint will report `status: "incomplete"` for these partial assessments.

Question bank: `backend/data/questions.json` — 15 questions. Five core questions are given to everyone; the remaining questions are role-specific (`support`, `engineering`, `sales`, `manager`) and gated by `min_seniority`.

## AI mode

- `AI_MODE=mock` (default) returns canned responses from `backend/data/mock_ai_responses.json`, chosen by hashing the answer. Like a real model, the canned outputs are **not always well-formed** (e.g. `score: 7`, `score: "four"`, unknown flags, or missing `reason`). The validity rules in `completed_responses` reject such answers for dashboard/privacy counts.
- `AI_MODE=live` calls `LLM_API_URL` with `LLM_API_KEY` and `LLM_MODEL` (OpenAI-compatible chat completions).

---

## Known limitations and risks

- **Admin dashboard UI is a placeholder.** `Dashboard.jsx` prints raw JSON; the backend suppression logic is real and tested, but there is no polished dashboard.
- **Deletion scope is single-organization.** A multi-org user clicking delete only clears the selected organization; the others remain until deleted separately. This matches the current reading of the client request but is unconfirmed.
- **Secrets hygiene.** `backend/.env` exists in the working tree and contains a short `SECRET_KEY`. It is now covered by `.gitignore`, but if it was previously committed it must be removed from tracking (`git rm --cached backend/.env`) and rotated.
- **No LLM response-schema validation.** `score_open_answer` trusts the model's JSON. Malformed output (bad score types, unknown flags, missing reason) can be stored on submit; those rows simply do not count as valid assessments. A production build should validate the model output.
- **Two different maturity bandings.** The personal report uses `maturity_level` (bands at 2/3/4); the dashboard uses `level_for` (bands at 1.5/2.5/3.5). They can label the same average differently.
- **CORS is wide open** (`allow_origins=["*"]`), which is fine for local demos but not for production.
- **Live mode is untested.** All tests and local runs use `AI_MODE=mock`; the live HTTP path in [llm.py](backend/app/services/llm.py) has not been exercised.
- **The Stage 5 improvement plan depends on stored data.** If an assessment is empty, partial, or deleted, the endpoint returns an `empty`/`incomplete` state rather than inventing evidence. MCQ areas never have a written rationale because the schema does not store one.

## AI-tool usage

Portions of this work were produced with an AI coding assistant, then reviewed and corrected by hand:

- **AI helped with:** scaffolding the Stage 5 service/endpoint shape, drafting the README and demo script, and proposing test cases.
- **Independently reviewed:** every claim about scoring, privacy thresholds, deletion scope, and seniority filtering was checked against the actual code (`assessment.py`, `dashboard.py`, `questions.py`, `reports.py`) rather than accepted from the assistant. Data-grounded details (score bands, allowed flags, question metadata) were verified against `data/questions.json`, `mock_ai_responses.json`, and `llm.py`.
- **Concrete correction:** the assistant's first version of the Stage 5 recommendation ranking sorted candidate areas **purely by score**. Because a flagged open answer can score higher than the multiple-choice gaps, that ordering could drop the risk-flag recommendation entirely. The regression test `test_risk_flag_produces_supported_recommendation` failed, and the ranking was corrected to prioritise flagged areas before lowest scores. The fix is in `_recommendations` in [improvement.py](backend/app/services/improvement.py).

## Repository layout

```
ai-pulse-git/
├── CLIENT_REQUEST.md
├── README.md
├── DEMO.md
├── .gitignore
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/            # FastAPI application (routes/, services/, models, auth)
│   ├── data/           # questions.json, mock_ai_responses.json
│   └── tests/          # pytest suite
└── frontend/
    ├── package.json
    ├── vite.config.js
    └── src/            # React app (api.js, App.jsx, pages/)
```
