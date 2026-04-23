import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { cancelJob, fetchJobProgress } from "../lib/api";
import { getJobMeta, saveJobMeta } from "../lib/jobStorage";
import { MetricCard } from "../components/MetricCard";
import { ProgressBar } from "../components/ProgressBar";

export function ProgressPage() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const [progress, setProgress] = useState(() => {
    const saved = getJobMeta(jobId);
    return {
      percent: 0,
      processed: 0,
      total: saved?.total || 0,
      valid: saved?.valid || 0,
      risky: saved?.risky || 0,
      invalid: saved?.invalid || 0,
      status: saved?.status || "running",
    };
  });
  const [statusText, setStatusText] = useState("Preparing your verification job...");
  const [errorMessage, setErrorMessage] = useState("");
  const [isCancelling, setIsCancelling] = useState(false);
  const hasRedirectedRef = useRef(false);
  const savedMeta = getJobMeta(jobId);

  useEffect(() => {
    let isMounted = true;

    async function loadProgress() {
      try {
        const data = await fetchJobProgress(jobId);
        if (!isMounted) {
          return;
        }

        const nextProgress = {
          percent: data.percent ?? 0,
          processed: data.processed ?? 0,
          total: data.total ?? 0,
          valid: data.valid ?? 0,
          risky: data.risky ?? 0,
          invalid: data.invalid ?? 0,
          status: data.status || "running",
        };

        setProgress(nextProgress);
        setStatusText(buildStatusText(nextProgress));
        setErrorMessage("");
        saveJobMeta({
          jobId,
          total: nextProgress.total,
          valid: nextProgress.valid,
          risky: nextProgress.risky,
          invalid: nextProgress.invalid,
          status: nextProgress.status,
          fileName: savedMeta?.fileName,
        });

        if (
          !hasRedirectedRef.current &&
          (nextProgress.status === "done" ||
            nextProgress.status === "cancelled" ||
            (nextProgress.total > 0 && nextProgress.processed >= nextProgress.total))
        ) {
          hasRedirectedRef.current = true;
          navigate(`/jobs/${jobId}/results`, { replace: true });
        }
      } catch (error) {
        if (!isMounted) {
          return;
        }

        setErrorMessage(
          error.response?.data?.error || error.message || "We could not load progress.",
        );
      }
    }

    loadProgress();
    const intervalId = window.setInterval(loadProgress, 2000);

    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, [jobId, navigate, savedMeta?.fileName]);

  async function handleCancel() {
    setIsCancelling(true);
    setErrorMessage("");

    try {
      await cancelJob(jobId);
      setStatusText("Cancellation requested. Finalizing your job...");
      setProgress((current) => ({
        ...current,
        status: "cancelling",
      }));
    } catch (error) {
      setErrorMessage(
        error.response?.data?.error || error.message || "We could not cancel the job.",
      );
    } finally {
      setIsCancelling(false);
    }
  }

  return (
    <section className="page-grid page-grid-progress">
      <div className="panel panel-large">
        <div className="panel-header">
          <div>
            <span className="eyebrow">Verification Progress</span>
            <h1>We’re checking your list in real time.</h1>
          </div>
          <span className="chip">{savedMeta?.fileName || "Active job"}</span>
        </div>

        <div className="progress-hero">
          <div>
            <div className="progress-number">{progress.percent}%</div>
            <p className="progress-subcopy">{statusText}</p>
          </div>
          <div className="progress-detail-card">
            <span>Processed</span>
            <strong>
              {progress.processed.toLocaleString()} of {progress.total.toLocaleString()}
            </strong>
          </div>
        </div>

        <ProgressBar value={progress.percent} />

        <div className="metrics-grid">
          <MetricCard eyebrow="Accepted" title="Valid emails" value={progress.valid} tone="valid" />
          <MetricCard eyebrow="Review" title="Risky emails" value={progress.risky} tone="risky" />
          <MetricCard eyebrow="Rejected" title="Invalid emails" value={progress.invalid} tone="invalid" />
        </div>

        {errorMessage ? <p className="inline-error">{errorMessage}</p> : null}

        <div className="panel-actions">
          <button
            className="ghost-button"
            disabled={isCancelling}
            onClick={handleCancel}
            type="button"
          >
            {isCancelling ? "Cancelling..." : "Cancel"}
          </button>
        </div>
      </div>

      <aside className="panel progress-side-panel">
        <span className="eyebrow">Live Notes</span>
        <h2>What happens next</h2>
        <ul className="info-list">
          <li>Syntax, duplicates, role accounts, disposable domains, and MX checks run first.</li>
          <li>Only clean candidates reach the SMTP probe layer on the probe server.</li>
          <li>When processing finishes, you’ll be redirected to downloads automatically.</li>
        </ul>
      </aside>
    </section>
  );
}

function buildStatusText(progress) {
  if (progress.status === "cancelled") {
    return "This job was cancelled. We’re taking you to the partial results.";
  }

  if (progress.total > 0 && progress.processed >= progress.total) {
    return "Verification complete. Preparing your results view.";
  }

  return `${progress.processed.toLocaleString()} of ${progress.total.toLocaleString()} emails processed`;
}
