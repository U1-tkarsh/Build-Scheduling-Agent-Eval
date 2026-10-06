export default function EvalResults({ data, loading, error }) {
  if (loading) {
    return <p className="muted">Running evaluation suite…</p>;
  }
  if (error) {
    return <p className="error">{error}</p>;
  }
  if (!data) {
    return (
      <p className="muted">
        Run the baseline suite, or run the full improvement loop to compare v1 → v2.
      </p>
    );
  }

  // Support both plain summary and improvement-loop payload
  const baseline = data.baseline || data;
  const rerun = data.rerun;
  const decision = data.decision;
  const improvement = data.improvement;

  return (
    <div className="eval-results">
      <SummaryCard title="Baseline" summary={baseline} />
      {improvement?.primary && (
        <section className="panel">
          <h3>Structured Improvement</h3>
          <pre className="code-block">{JSON.stringify(improvement.primary, null, 2)}</pre>
        </section>
      )}
      {rerun && <SummaryCard title="After Improvement" summary={rerun} />}
      {decision && (
        <section className="panel">
          <h3>Acceptance Decision</h3>
          <p>
            <strong>{decision.accepted ? "Accepted" : "Rejected"}</strong> — {decision.reason}
          </p>
          <p>
            Score {decision.old_score} → {decision.new_score}. Regressions:{" "}
            {(decision.regressions || []).length}
          </p>
        </section>
      )}
    </div>
  );
}

function SummaryCard({ title, summary }) {
  const results = summary.results || [];
  const failures = summary.failures || results.filter((r) => !r.passed);
  return (
    <section className="panel">
      <div className="panel-header">
        <h3>
          {title} · Version {summary.prompt_version || "—"}
        </h3>
        <span className="badge">Score {summary.score}%</span>
      </div>
      <div className="stat-row">
        <span>Passed: {summary.passed}</span>
        <span>Failed: {summary.failed}</span>
        <span>Total: {summary.total}</span>
      </div>
      <ul className="result-list">
        {results.map((r) => (
          <li key={r.scenario_id} className={r.passed ? "pass" : "fail"}>
            <span>{r.passed ? "PASS" : "FAIL"}</span>
            <span>{r.scenario_id}</span>
            <span>{r.score}</span>
          </li>
        ))}
      </ul>
      {failures.length > 0 && (
        <div className="failures">
          <h4>Failures</h4>
          {failures.map((f) => (
            <div key={f.scenario_id} className="failure-item">
              <strong>{f.scenario_id}</strong>
              <p>{f.failure?.message || "Failed checks"}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
