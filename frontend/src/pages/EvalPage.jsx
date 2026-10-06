import { useState } from "react";
import EvalResults from "../components/EvalResults";
import { runEvals } from "../api";

export default function EvalPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleRun(improve) {
    setLoading(true);
    setError("");
    try {
      const result = await runEvals({ improve, promptVersion: "v1" });
      setData(result);
    } catch (err) {
      setError(err.message || "Eval run failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Evaluation Dashboard</h1>
        <p>Deterministic scenarios, failure analysis, and regression-safe prompt promotion.</p>
      </header>
      <div className="actions">
        <button type="button" onClick={() => handleRun(false)} disabled={loading}>
          Run Baseline (v1)
        </button>
        <button type="button" onClick={() => handleRun(true)} disabled={loading}>
          Apply Improvement Loop
        </button>
      </div>
      <EvalResults data={data} loading={loading} error={error} />
    </div>
  );
}
