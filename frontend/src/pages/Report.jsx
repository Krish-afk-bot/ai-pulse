import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const SCOPE_LABELS = {
  core: "Core AI practice (all roles)",
  role_specific: "Role-specific practice",
};

function EvidenceAreas({ areas }) {
  if (!areas.length) return <p>No saved answers are available.</p>;
  return (
    <ul className="evidence-list">
      {areas.map((area) => (
        <li key={area.question_id}>
          <p>
            <b>{area.question}</b> <em>({SCOPE_LABELS[area.scope] || area.scope})</em>
          </p>
          <p>Your answer: “{area.answer}” — score {area.score}/5</p>
          <p>
            Scoring rationale:{" "}
            {area.rationale_available ? area.rationale : <span className="muted">Not stored. {area.rationale_note}</span>}
          </p>
          {area.flags.length > 0 && <p className="error">Risk flags: {area.flags.join(", ")}</p>}
        </li>
      ))}
    </ul>
  );
}

export default function Report() {
  const [report, setReport] = useState(null);
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deleting, setDeleting] = useState(false);

  async function loadReport() {
    try {
      const [reportData, planData] = await Promise.all([
        api("/reports/me"),
        api("/reports/me/improvement"),
      ]);
      setReport(reportData);
      setPlan(planData);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadReport();
  }, []);

  async function deleteResponses() {
    if (!window.confirm("Delete your assessment answers and report for this organization? This cannot be undone.")) return;
    setDeleting(true);
    setError("");
    setNotice("");
    try {
      await api("/reports/me", { method: "DELETE" });
      setReport(null);
      setPlan(null);
      setNotice("Your assessment answers and report have been deleted for this organization.");
      await loadReport();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeleting(false);
    }
  }

  if (!report) return <div className="card">{error ? <p className="error" role="alert">{error}</p> : <p>Loading…</p>}</div>;
  return (
    <div className="card">
      <h2>{report.name}: {report.level}</h2>
      <p>Average score: {report.average_score}</p>
      <h3>Risks</h3>
      <ul>{report.risks.map((r) => <li key={r}>{r}</li>)}</ul>
      <h3>Next steps</h3>
      <ul>{report.next_steps.map((s) => <li key={s}>{s}</li>)}</ul>

      {plan && <ImprovementPlan plan={plan} />}

      {notice && <p role="status">{notice}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <button type="button" onClick={deleteResponses} disabled={deleting}>
        {deleting ? "Deleting…" : "Delete my assessment data"}
      </button>
    </div>
  );
}

function ImprovementPlan({ plan }) {
  return (
    <section aria-labelledby="improvement-heading">
      <h3 id="improvement-heading">Your assessment evidence and improvement plan</h3>
      <p className="muted">{plan.note}</p>

      {plan.status !== "available" ? (
        <p role="status">{plan.message}</p>
      ) : (
        <>
          {plan.message && <p role="status">{plan.message}</p>}

          <h4>Skill areas and evidence</h4>
          <EvidenceAreas areas={plan.areas} />

          <h4>Improvement opportunities</h4>
          {plan.gaps.length === 0 ? (
            <p>No improvement opportunities were found below the threshold.</p>
          ) : (
            <ul>
              {plan.gaps.map((gap) => (
                <li key={gap.question_id}>
                  {gap.question}: {gap.reason}
                  {gap.flags.length > 0 && <> (risk flags: {gap.flags.join(", ")})</>}
                </li>
              ))}
            </ul>
          )}

          <h4>Recommended next actions</h4>
          <ol>
            {plan.recommendations.map((rec, index) => (
              <li key={`${rec.source}-${index}`}>
                <p>{rec.action}</p>
                <p className="muted">{rec.explanation}</p>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
