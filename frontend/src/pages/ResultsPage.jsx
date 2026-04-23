import { useEffect, useState } from "react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Link, useNavigate, useParams } from "react-router-dom";
import { MetricCard } from "../components/MetricCard";
import { buildDownloadUrl, fetchJobProgress } from "../lib/api";
import { getJobMeta, saveJobMeta } from "../lib/jobStorage";

const PIE_COLORS = ["#22c55e", "#f59e0b", "#ef4444"];

export function ResultsPage() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const savedMeta = getJobMeta(jobId);
  const [summary, setSummary] = useState({
    valid: savedMeta?.valid || 0,
    risky: savedMeta?.risky || 0,
    invalid: savedMeta?.invalid || 0,
    total: savedMeta?.total || 0,
    status: savedMeta?.status || "running",
  });
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let isMounted = true;

    async function loadSummary() {
      try {
        const data = await fetchJobProgress(jobId);
        if (!isMounted) {
          return;
        }

        const nextSummary = {
          valid: data.valid ?? 0,
          risky: data.risky ?? 0,
          invalid: data.invalid ?? 0,
          total: data.total ?? 0,
          status: data.status || "running",
        };

        setSummary(nextSummary);
        saveJobMeta({
          jobId,
          total: nextSummary.total,
          valid: nextSummary.valid,
          risky: nextSummary.risky,
          invalid: nextSummary.invalid,
          status: nextSummary.status,
          fileName: savedMeta?.fileName,
        });
        setErrorMessage("");

        if (
          nextSummary.status !== "done" &&
          nextSummary.status !== "cancelled" &&
          nextSummary.total > 0 &&
          nextSummary.valid + nextSummary.risky + nextSummary.invalid < nextSummary.total
        ) {
          navigate(`/jobs/${jobId}/progress`, { replace: true });
        }
      } catch (error) {
        if (!isMounted) {
          return;
        }

        setErrorMessage(
          error.response?.data?.error || error.message || "We could not load the results yet.",
        );
      }
    }

    loadSummary();
    return () => {
      isMounted = false;
    };
  }, [jobId, navigate, savedMeta?.fileName]);

  const chartData = [
    { name: "Safe to Send", value: summary.valid },
    { name: "Risky", value: summary.risky },
    { name: "Invalid", value: summary.invalid },
  ];

  return (
    <section className="page-grid page-grid-results">
      <div className="panel panel-large">
        <div className="panel-header">
          <div>
            <span className="eyebrow">Results</span>
            <h1>Your verification breakdown is ready.</h1>
          </div>
          <span className="chip">
            {summary.status === "cancelled" ? "Cancelled job" : savedMeta?.fileName || "Completed job"}
          </span>
        </div>

        <div className="metrics-grid metrics-grid-results">
          <MetricCard
            eyebrow="✅ Safe to Send"
            title="Verified deliverable emails"
            value={summary.valid}
            tone="valid"
          />
          <MetricCard eyebrow="⚠️ Risky" title="Catch-all or timeout emails" value={summary.risky} tone="risky" />
          <MetricCard eyebrow="❌ Invalid" title="Rejected or unusable emails" value={summary.invalid} tone="invalid" />
        </div>

        <div className="download-grid">
          <a className="download-button" href={buildDownloadUrl(jobId, "safe")}>
            Download Safe to Send
          </a>
          <a className="download-button" href={buildDownloadUrl(jobId, "full")}>
            Download Full List
          </a>
          <a className="download-button" href={buildDownloadUrl(jobId, "risky")}>
            Download Risky
          </a>
          <a className="download-button" href={buildDownloadUrl(jobId, "invalid")}>
            Download Invalid
          </a>
        </div>

        {errorMessage ? <p className="inline-error">{errorMessage}</p> : null}

        <div className="results-footer">
          <Link className="ghost-link" to="/">
            Verify another file
          </Link>
        </div>
      </div>

      <aside className="panel chart-panel">
        <div className="panel-header">
          <div>
            <span className="eyebrow">Distribution</span>
            <h2>Outcome overview</h2>
          </div>
        </div>

        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height={320}>
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                innerRadius={78}
                outerRadius={112}
                dataKey="value"
                paddingAngle={3}
              >
                {chartData.map((entry, index) => (
                  <Cell fill={PIE_COLORS[index % PIE_COLORS.length]} key={entry.name} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value) => [Number(value).toLocaleString(), "Emails"]}
                contentStyle={{
                  borderRadius: 16,
                  border: "1px solid rgba(99, 102, 241, 0.18)",
                  boxShadow: "0 18px 40px rgba(15, 23, 42, 0.12)",
                }}
              />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-caption">
          <strong>{summary.total.toLocaleString()} total emails</strong>
          <span>Use filtered downloads to move directly from results into campaign prep.</span>
        </div>
      </aside>
    </section>
  );
}
