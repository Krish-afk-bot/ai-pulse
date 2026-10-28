import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Report() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deleting, setDeleting] = useState(false);

  async function loadReport() {
    try {
      setReport(await api("/reports/me"));
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
      setNotice("Your assessment answers and report have been deleted for this organization.");
      await loadReport();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeleting(false);
    }
  }

  if (!report) return <div className="card">{error ? <p className="error">{error}</p> : <p>Loading…</p>}</div>;
  return (
    <div className="card">
      <h2>{report.name}: {report.level}</h2>
      <p>Average score: {report.average_score}</p>
      <h3>Risks</h3>
      <ul>{report.risks.map((r) => <li key={r}>{r}</li>)}</ul>
      <h3>Next steps</h3>
      <ul>{report.next_steps.map((s) => <li key={s}>{s}</li>)}</ul>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <button type="button" onClick={deleteResponses} disabled={deleting}>
        {deleting ? "Deleting…" : "Delete my assessment data"}
      </button>
    </div>
  );
}
