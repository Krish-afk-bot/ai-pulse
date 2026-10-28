# AI Pulse

AI Pulse helps a company see how well its people use AI at work, team by team,
without exposing individuals. Employees take a short diagnostic that adapts to
their role and seniority. Leadership sees team results under a privacy rule.

**Walkthrough video:** [ADD LINK BEFORE SUBMITTING]

## Quick start

Backend (Python 3.12 or 3.13):

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put a random value in SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
python -m app.seed          # demo data. Drops all tables. Password for every user: pulse123
uvicorn app.main:app --reload
```

Frontend (second terminal):

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

Tests: `cd backend && python -m pytest -q` (69 passed) and `cd frontend && npm run build`.

## Demo accounts (password `pulse123`)

| Account | What to look at |
|---|---|
| asha@northwind.test | Northwind admin. Dashboard is empty by design: every seeded team is under 5 completed diagnostics. |
| meera@bluepeak.test | Bluepeak admin. Same. |
| ravi@consult.test | Both orgs: employee at Northwind, admin at Bluepeak. The token is scoped to the org you pick. |
| priya@northwind.test | Support employee. Report, improvement plan, delete button. |
| dev@northwind.test | Engineering lead. Gets the senior engineering questions. |

## In three minutes

- **Found:** the dashboard trusted `?org_id`; a secret was committed and let anyone forge a login; the dashboard average was wrong; leads lost senior questions; bad AI output crashed or polluted data.
- **Fixed:** tenant isolation, secret untracked, scoring validation that is strict but tolerant, seniority ranking, error handling, plus the two client requests.
- **Deliberately left:** password hashing, CORS, dashboard UI, live-model testing (see below).
- **Client request:** teams under 5 completed diagnostics are hidden; employees can delete their own answers per organization.
- **Own feature:** an evidence-backed improvement plan on the employee report.
- **Tests:** original commit `5e3713c`: 1 failed, 7 passed. Now: 69 passed.

## What I found

All reproduced on the original code (commit `5e3713c`).

**Tenant isolation and auth**
- `routes/dashboard.py:24` trusted `?org_id`. A Bluepeak admin read Northwind's departments and risks.
- `routes/auth_routes.py:33` issued a token for any `org_id` without checking membership.
- `backend/.env` was tracked with `SECRET_KEY=pulse-7f3a9c2e1b-prod`. A token signed with it, without any login, returned the Northwind admin dashboard (HTTP 200). **The key is still in git history and must be rotated.**
- `tests/test_api.py::test_admin_cannot_see_other_org` called the admin's own org and asserted 200. The leak was green.

**Numbers and questions**
- `routes/dashboard.py:48` divided by headcount, not responses. Sales showed 2.67 when its only respondent scored 4.0. Empty teams showed `0.0 / Beginner`.
- The dashboard and the report used different maturity bands (1.5/2.5/3.5 vs 2/3/4).
- `services/questions.py:18` compared seniority as strings, so `"lead" < "mid"`. Leads lost the senior questions. This was the one failing baseline test.

**AI output**
- `services/scoring.py:8-9` ran `json.loads` unguarded and stored the result unchecked. Of the 10 canned model outputs, one crashed the request, and others carried a score of 7, `"four"`, a missing reason, or an invented flag `probably_lying`.
- After my first, strict fix, about half of normal answers were rejected with 502. Measured: 21 of 40 answers in mock mode. The same text failed every time, and the UI showed no message.

**Other**
- Submitting twice stored duplicate answers (6 questions gave 14 stored answers).
- `backend/Dockerfile` started `main:app`, which does not exist.
- `frontend/src/pages/Diagnostic.jsx` showed no error when a request failed.

## What I fixed

| Fix | Where / tests |
|---|---|
| Dashboard uses the org from the token; a different `org_id` gets 403 | `test_admin_cannot_see_other_org`, `test_employee_cannot_access_admin_dashboard`, `test_dashboard_cross_tenant_access_still_denied` |
| `select-org` requires a membership | `tests/test_auth_select_org.py` |
| Secret untracked; no hard-coded fallback; old key rejected | `tests/test_auth_secret.py` |
| Average computed per person, not per headcount | `routes/dashboard.py` |
| Seniority ranking | `test_lead_manager_gets_policy_questions` and the other tests in `test_questions.py` |
| Model output: first JSON object extracted, whole number 1-5 only (never clamped), unknown flags dropped, default reason, one retry, then `ScoringError` (502, nothing saved) | `tests/test_scoring_validation.py`, one case per fixture in `data/mock_ai_responses.json` |
| Small groups hidden; flags from hidden teams excluded | `tests/test_privacy_deletion.py` |
| Delete my answers, per organization, immediate effect | `tests/test_privacy_deletion.py` |
| Duplicate and unassigned answers do not count as completed | `completed_responses` in `services/assessment.py` |
| Frontend error states; `api.js` no longer crashes on non-JSON errors | manual browser check |
| Dockerfile entrypoint `app.main:app` | not built (Docker not available) |

Tests I changed: `test_admin_cannot_see_other_org` now asserts 403 instead of 200.

## What I deliberately left, and why

- **SHA-256 password hashing** (`auth.py`). Real fix: a salted, slow hash. Not done in the time available.
- **CORS `*`** (`main.py`). Acceptable for local demos, not for production.
- **Admin dashboard UI** is a raw JSON view (`Dashboard.jsx`). The backend rules are tested.
- **Live model mode is untested.** Everything runs in mock mode.
- **Prompt injection is not fully handled.** A user can still try to steer the score of their open answer.
- **No login throttling, no password reset, no account creation.**
- **Two maturity functions** may still exist in the code (`utils.py` and `dashboard.py`). [CONFIRM IN CODE BEFORE KEEPING THIS LINE]
- **Old secret is still in git history.** Rotate it.

## The client request

**1. No small groups.** A department is returned only when at least 5 distinct people have a complete, valid diagnostic. Below that, the department is skipped entirely: no name, score or risk. `top_risks` counts only released departments, and a flag must be seen for at least 5 different people. Completeness comes from `completed_responses` (`services/assessment.py`).

**2. Right to delete.** `DELETE /reports/me` removes the signed-in employee's answers in the selected organization. It takes no user id, so nobody can delete another person's data. The dashboard re-reads data on every request, so the change shows immediately. Admins get 403.

## Questions for Northwind HR

1. Delete: only the selected organization, or all organizations for a consultant like Ravi?
2. Hard delete, or soft delete for audit?
3. Does "completed" mean the whole question set (what I built)?
4. Hide small teams (what I built) or group them as "Other teams"?
5. Is it acceptable that a risk only appears when 5 or more people share it? This hides real risks in small companies.
6. Can admins or HR delete data on someone's behalf (for example a leaver)?
7. Where else does the data live: backups, and the LLM provider in live mode (free text goes to a third party)?

## My feature: improvement plan

`GET /reports/me/improvement` returns, for the signed-in employee only: the saved answer, score and reason per question; the gaps (score below 4); and 2-3 recommended next actions, each tied to stored evidence. It never invents evidence: if there is no or partial data it returns `empty` or `incomplete`.

**Problem:** the report gave a number and a level but no reason and no next step. **Why this one:** [YOUR REASON]. It reuses stored data, adds no model call, and cannot read another person's plan. Tests: `tests/test_improvement_plan.py`.

## Can the AI parts be trusted?

- **Output is validated** (`services/scoring.py`): the first JSON object is extracted, even from a code fence; the score must be a whole number 1-5; unknown flags are dropped; one retry; then 502 and nothing saved. All 10 mock fixtures are tested.
- **In mock mode** (the default), the response is picked by hashing the answer, so it is deterministic. Of 40 different answers, [N] still failed (score 7 and `"four"` are the two invalid fixtures).
- **Limits:** live mode is untested, and the prompt is not hardened against injection.

## How to change it safely

| What | Where |
|---|---|
| Questions | `backend/data/questions.json`, tests in `tests/test_questions.py` |
| Privacy threshold | the `5` in `routes/dashboard.py` |
| Scoring | `services/scoring.py`, `services/llm.py` |
| Auth | `auth.py`, `routes/auth_routes.py` |
| UI | `frontend/src/pages/` |

Run one test: `cd backend && python -m pytest tests/test_privacy_deletion.py -q`

## Verification

- Backend: **69 passed**. Original commit: 1 failed, 7 passed.
- Frontend: `npm run build` succeeds.
- **Not run:** Docker image, live model, CI on GitHub.

## How I used AI

I used an AI coding assistant to read the code, draft fixes, write tests and draft this document. I ran the tests myself and checked claims against the code.

**One place it was wrong:** its first ranking of improvement recommendations sorted by score only, so a flagged open answer could drop out of the plan. `test_risk_flag_produces_supported_recommendation` failed, and the ranking now puts flagged areas first (`_recommendations` in `services/improvement.py`). [KEEP ONLY IF THIS HAPPENED IN YOUR WORK]

## Known limitations

- Delete is per organization; the "all organizations" question is open.
- Live model path and prompt injection: see above.
- The old secret is in git history.