import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Diagnostic({ onDone }) {
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api("/diagnostic/questions").then(setQuestions);
  }, []);

  async function submit() {
    setError("");
    setSaving(true);
    try {
      const payload = Object.entries(answers).map(([question_id, answer]) => ({ question_id, answer }));
      await api("/diagnostic/submit", { method: "POST", body: JSON.stringify({ answers: payload }) });
      onDone();
    } catch (err) {
      // 502 means the scoring model gave an unusable answer; anything else
      // (e.g. a 400 validation message) is shown as the server sent it.
      if (err.status === 502) {
        setError("We could not score one of your answers just now. Please try again in a moment.");
      } else {
        setError(err.message || "Something went wrong. Please try again.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <h2>Your AI diagnostic</h2>
      {questions.map((q) => (
        <div key={q.id}>
          <p><b>{q.text}</b></p>
          {q.type === "mcq" ? (
            <select onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} defaultValue="">
              <option value="" disabled>Choose…</option>
              {q.options.map((o) => <option key={o}>{o}</option>)}
            </select>
          ) : (
            <textarea rows={4} onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} />
          )}
        </div>
      ))}
      {error && <p className="error" role="alert">{error}</p>}
      <button onClick={submit} disabled={saving}>{saving ? "Submitting…" : "Submit"}</button>
    </div>
  );
}
