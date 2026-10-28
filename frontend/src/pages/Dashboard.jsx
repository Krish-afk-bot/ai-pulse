import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const RISK_LABELS = {
  customer_data_shared: "Customer data shared with an AI tool",
  confidential_data_shared: "Confidential data shared with an AI tool",
  unreviewed_output: "Output used without review",
  policy_unaware: "Unaware of the AI policy",
};

export default function Dashboard({ org }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api(`/dashboard?org_id=${org.org_id}`)
      .then(setData)
      .catch((err) => setError(err.message));
  }, [org]);

  if (error) {
    return (
      <div className="card">
        <p className="error" role="alert">{error}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="card">
        <p>Loading…</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>{data.organization}</h2>

      {data.departments.length === 0 ? (
        <p role="status">
          No group has enough completed diagnostics to show yet. Results appear once at least{" "}
          {data.min_group_size} people in a group have finished.
        </p>
      ) : (
        <>
          <table className="dashboard-table">
            <caption>Completed diagnostics by team</caption>
            <thead>
              <tr>
                <th scope="col">Team</th>
                <th scope="col">People</th>
                <th scope="col">Completed</th>
                <th scope="col">Average score</th>
                <th scope="col">Level</th>
              </tr>
            </thead>
            <tbody>
              {data.departments.map((row) => (
                <tr key={row.department} className={row.is_group ? "group-row" : ""}>
                  <th scope="row">{row.department}</th>
                  <td>{row.employees}</td>
                  <td>{row.responded}</td>
                  <td>{row.average_score ?? "—"}</td>
                  <td>{row.level}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <p className="muted">
            Teams with fewer than {data.min_group_size} completed diagnostics are combined here, and
            hidden entirely if the combined group is also under {data.min_group_size}.
          </p>

          <h3>Top risks</h3>
          {data.top_risks.length === 0 ? (
            <p className="muted">No risk is shared by enough people to report yet.</p>
          ) : (
            <ul>
              {data.top_risks.map(([flag, people]) => (
                <li key={flag}>{RISK_LABELS[flag] || flag}: {people} people</li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
