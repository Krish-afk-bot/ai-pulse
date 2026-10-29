# AI Pulse

AI Pulse shows how well a company's teams use AI at work without exposing individuals. Employees take a short diagnostic that adapts to their role and seniority; leadership sees only aggregate, privacy-safe results.

[![CI](https://github.com/Krish-afk-bot/ai-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/Krish-afk-bot/ai-pulse/actions/workflows/ci.yml)

## Run it

PowerShell, one command per line, no `&&`. Backend first:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
python -m app.seed
uvicorn app.main:app --reload
```

Put the printed value in `SECRET_KEY` in `backend/.env` before starting. `app.seed` drops and recreates the tables. The backend runs on http://localhost:8000.

Frontend, in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Frontend on http://localhost:5173. Tests:

```powershell
cd backend
python -m pytest -q -W ignore
```

Demo accounts, all with password `pulse123`:

| Account | What to look at |
|---|---|
| asha@northwind.test | Northwind admin. Dashboard table and top risks. |
| meera@bluepeak.test | Bluepeak admin. Only two completed diagnostics, so nothing is released. |
| ravi@consult.test | Employee at Northwind, admin at Bluepeak. Same password, two roles. |
| priya@northwind.test | Support junior. Starts with two partial answers, so she can finish live. |
| dev@northwind.test | Engineering lead. Gets the senior engineering questions. |

`AI_MODE` defaults to `mock`, which picks a canned response by hashing the answer text, so scoring is deterministic. The app logs a warning at startup in that mode, because it must not be used for a real assessment. `live` calls an OpenAI-compatible endpoint and needs `LLM_API_URL`, `LLM_API_KEY` and `LLM_MODEL`; without them the app refuses to start rather than fail on the first answer.

If you reseed, the rows are recreated with new ids, so a token left in `localStorage` can point at a different person. Run `localStorage.clear()` in the browser console and sign in again. The same happens after every backend restart when `SECRET_KEY` is unset, because a new random key is generated each time.

## 1. What I found, fixed, and left

The first column describes the original code, which I compared against commit `5e3713c`.

| Problem | Status | Notes |
|---|---|---|
| Dashboard read `?org_id` from the query string | Fixed | An admin of one org could read another org's departments and risks. `routes/dashboard.py` now returns 403 unless the caller is an admin of the org in their token. `test_admin_cannot_see_other_org`, `test_dashboard_cross_tenant_access_still_denied`. |
| `select-org` issued a token for any org id | Fixed | `routes/auth_routes.py` checks for a real membership first. `test_auth_select_org.py`. |
| `backend/.env` was tracked, with `SECRET_KEY=pulse-7f3a9c2e1b-prod` | Left | The key is dead: `config.py` has no hard-coded fallback and signs with a fresh random key when `SECRET_KEY` is unset, and `test_auth_secret.py` proves the old key can no longer sign a valid token. It is still in git history and must be rotated. TODO: verify that `.env` is no longer tracked, with `git ls-files backend/.env`. |
| Passwords hashed with plain, unsalted SHA-256 | Fixed | `auth.py` uses `hashlib.scrypt` (N=16384, r=8, p=1, 16-byte salt), stores the parameters inside the hash, and upgrades a legacy hash on the next successful login. `test_password_hashing.py`. |
| Seniority compared as strings, so `"lead" < "mid"` | Fixed | Leads silently lost the senior questions. `services/questions.py` now uses `SENIORITY_RANK`. `test_questions.py`. |
| Model output parsed with a bare `json.loads` and stored unchecked | Fixed | `services/scoring.py` extracts the first JSON object, requires a whole number 1-5, drops unknown flags, defaults a missing reason, retries once, then raises `ScoringError` (502, nothing saved). `test_scoring_validation.py`. |
| The answer travelled in the same message as the scoring rules | Reduced, not solved | `services/llm.py` sends the rules as a `system` message and the answer alone inside `<employee_answer>`, strips those tags out of the answer, and sets `temperature: 0`. A model that ignores its instructions can still be misled. |
| `AI_MODE` defaults to `mock`, so a deployment that forgets to set it silently scores everyone with canned answers | Left | The default stands. `config.py` now rejects any other value and requires the three LLM variables in live mode, and `main.py` warns at startup. |
| A double submit created duplicate rows for the same question | Fixed | Duplicates made `completed_responses` reject that person forever. There is now a `UniqueConstraint("membership_id", "question_id")` on `Response` and the submit route returns 409 on `IntegrityError`. `test_response_uniqueness.py`. |
| Two maturity bandings (`1.5/2.5/3.5` on the dashboard, `2/3/4` on the report) | Fixed | `utils.maturity_level` is the only one; `dashboard.py` imports it. `test_maturity_bands.py`. |
| Admin dashboard rendered raw JSON | Fixed | `frontend/src/pages/Dashboard.jsx` is a table with a caption and `th scope="col"`, a plain-English top-risks list, and an empty state that does not reveal how many people finished. |
| No CI | Fixed | `.github/workflows/ci.yml` runs the backend tests and the frontend build on push and pull request to `main`. |
| Department average divided by headcount, not by responses | Fixed | `routes/dashboard.py` averages each person's own average, then averages those, and only over people with a complete assessment. |
| Dockerfile started `main:app`, which does not exist | Fixed | It starts `app.main:app`. TODO: verify by building the image; Docker was not available here. |

Left on purpose:

| Left | Why |
|---|---|
| CORS `allow_origins=["*"]` in `main.py` | Fine for a local demo, wrong for anything public. |
| Token in `localStorage` (`frontend/src/api.js`) | Simple, but any script on the page can read it. An httpOnly cookie is the real fix. |
| No migrations | `create_all` runs at startup and never alters an existing table, so the new unique constraint needs a reseed. Alembic is the answer. |
| No login rate limiting, no password reset, no signup | Out of scope for a pilot, and all three are needed before real use. |
| Delete is scoped to one organization | The client has not said what a multi-org user like Ravi should get. |
| "Other teams" numbers move when someone deletes data | Pooling is recomputed on every request, so one deletion can push a team back under the threshold and change the pooled row. Correct for privacy, awkward to explain. |
| N+1 queries in the dashboard | One query per member per request. Fine at seed size, not at a few thousand people. |
| Live mode tested only against a mocked endpoint | `test_llm_live.py` patches `httpx.post`. No real provider has ever been called. |

Honestly still weak: the injection defence is a delimiter and a sentence, not a guarantee. The old secret sits in history. There are no migrations. Nothing here has run against a real model.

## 2. The client request

**No small groups.** `GET /dashboard?org_id=...` releases a department only when at least `MIN_GROUP_SIZE` (5) distinct people in it have a complete, valid diagnostic. Below that the department is pooled into a single "Other teams" row, and that row is shown only if the pool itself reaches five; otherwise nothing is returned at all, not even a count. `top_risks` counts flags only from released rows, and a flag needs five distinct people. Validity comes from `completed_responses` in `services/assessment.py`, which rejects partial, duplicate or unassigned answers. Covered by `test_privacy_deletion.py`, `test_other_teams.py` and `test_seed_demo.py`.

**Right to delete.** `DELETE /reports/me` removes the signed-in employee's answers for the organization in their token and returns how many rows went. It takes no user id, so it can only ever delete your own data, and admins get 403. The dashboard reads the database on every request, so the change is visible immediately. Covered by `test_privacy_deletion.py`.

Questions I would put to Northwind:

1. Should delete cover every organization for a user like Ravi, or only the one they are signed into?
2. Can an admin who also takes the diagnostic delete their own answers? Right now they get 403.
3. Does "delete" reach backups too, and what is the retention period?
4. Is sending free-text answers to an external LLM acceptable, and if so which provider and which region?
5. Is five the right threshold for every team, including the small ones where it hides real risk?
6. Do you want an audit log of deletions, and who should be able to read it?

## 3. My own feature: the evidence-backed improvement plan

`GET /reports/me/improvement` (`routes/reports.py`, `services/improvement.py`) returns, for the signed-in employee only: their saved answer, score, stored rationale and risk flags per question; the areas below 4/5; and two or three next actions, each naming the answer or flag it came from. `frontend/src/pages/Report.jsx` renders it below the report.

The problem it solves: the report gave an average and a maturity label and stopped. It told someone they were a "Practitioner" without saying which answer cost them or what to do next. This answers "why this score" and "what now", using only data the assessment already stores. It marks clearly what is saved evidence and what is generated text.

Why this over other ideas: it needs no new model call, no new data and no new permission model, and it makes the privacy work visible instead of hidden behind an aggregate. I rejected a manager-facing scorecard because a per-person manager view would leak individual scores far more easily.

What it does not do: it never calls an LLM, it keeps no history, and there is no manager view. It cannot show progress over time, because there is only ever one current assessment.

One weakness, honestly: the ranking and the wording were too generic. Every gap was treated the same, and every multiple-choice gap aimed at the top option, so "A few times a month" jumped straight to "Many times a day" and someone who had not read the policy was told to help others follow it. Ranking now puts risk flags first, then the data, review and policy questions, then everything else, lowest score first, and asks for one level up rather than the top. `test_improvement_plan.py` covers each of those.

## 4. How I used AI tools

I used AI as a pair programmer and a reviewer, and kept the decisions and the verification myself.

- **Trae (AI coding agent):** implemented the fixes in small tasks, one at a time, with tests run after each.
- **Claude (chat):** acted as an independent reviewer. It probed my repository, listed suspected problems, and I only kept a finding when I could reproduce it. It also checked this README against the code and caught stale claims.
- **My decisions:** what to fix and what to leave (section 1), hiding small teams behind an "Other teams" pool, scoping delete to one organization, and which feature to build.
- **My verification:** I ran the tests and the build myself, compared against the original commit `5e3713c`, and removed any claim I could not back with code or command output.

**One place the AI got it wrong.** The first version of the model-output validation in `services/scoring.py` was too strict. It rejected the whole answer for a code-fenced JSON reply, an unknown risk flag, or a missing reason, so ordinary submissions failed with a 502. In mock mode the response depends only on the text, so the same answer failed every time, and the UI showed no error. The code and the AI-written tests both looked fine. A review pass that submitted 40 different answers exposed it: the strict version rejected 17 and the final version rejects 7, the genuinely invalid outputs (a score of 7 and `"four"`). The fix extracts the first JSON object, accepts only a whole-number 1-5 score, drops unknown flags, defaults a missing reason, and retries once. Each canned output has a test.

A second, smaller miss is in section 3: the first improvement-plan wording was generic and aimed every gap at the top option. I changed the ranking and added tests.

## Tests and CI

The backend suite covers tenant authorization, the select-org membership check, the old secret being rejected, seniority filtering, scoring validation and retries, every mock fixture, password hashing and the legacy upgrade, the privacy threshold, pooling, deletion and its effect on the dashboard, the unique constraint, the single maturity banding, the improvement plan, and the live scoring path with a mocked HTTP call.

What it does not cover: no real LLM call, no browser tests, no Docker build, no concurrency or load test. The frontend has no automated tests at all; `npm run build` only proves it compiles. The seeded numbers are checked by `test_seed_demo.py`, but nothing checks that the demo still looks right by eye.

TODO: verify the current test count and runtime by running `cd backend` then `python -m pytest -q -W ignore` and pasting the output. TODO: verify that the CI workflow passes on GitHub; it has not been pushed yet.

## What I would do next

1. Rotate the leaked secret and purge it from git history, then rotate anything else that ever lived in `.env`.
2. Add Alembic, so a deployment does not need a reseed to pick up a new constraint.
3. Fix the N+1 queries on the dashboard before it is pointed at a real company.
4. Move the token out of `localStorage`, add login rate limiting, and add an audit log for deletions.
5. Call a real model in staging with a cost and timeout budget, and re-test the prompt against injection.
