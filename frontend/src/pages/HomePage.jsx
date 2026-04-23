import { useState } from "react";
import { useDropzone } from "react-dropzone";
import { useNavigate } from "react-router-dom";
import { uploadVerificationFile } from "../lib/api";
import { inspectFile } from "../lib/fileAnalysis";
import { saveJobMeta } from "../lib/jobStorage";

const ACCEPTED_FILES = {
  "text/csv": [".csv"],
  "text/plain": [".txt"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
};

export function HomePage() {
  const navigate = useNavigate();
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileInfo, setFileInfo] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [isReadingFile, setIsReadingFile] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const dropzone = useDropzone({
    accept: ACCEPTED_FILES,
    multiple: false,
    onDropAccepted: async (files) => {
      const [file] = files;
      if (!file) {
        return;
      }

      setErrorMessage("");
      setIsReadingFile(true);

      try {
        const analysis = await inspectFile(file);
        setSelectedFile(file);
        setFileInfo(analysis);
      } catch (error) {
        setSelectedFile(null);
        setFileInfo(null);
        setErrorMessage(error.message || "We could not read that file.");
      } finally {
        setIsReadingFile(false);
      }
    },
    onDropRejected: () => {
      setSelectedFile(null);
      setFileInfo(null);
      setErrorMessage("Please upload a CSV, TXT, or XLSX file.");
    },
  });

  async function handleStartVerification() {
    if (!selectedFile || !fileInfo) {
      return;
    }

    setIsSubmitting(true);
    setErrorMessage("");

    try {
      const response = await uploadVerificationFile(selectedFile);
      saveJobMeta({
        jobId: response.job_id,
        fileName: fileInfo.fileName,
        total: fileInfo.rowCount,
      });
      navigate(`/jobs/${response.job_id}/progress`);
    } catch (error) {
      const message =
        error.response?.data?.error ||
        error.message ||
        "Verification could not be started.";
      setErrorMessage(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="page-grid page-grid-home">
      <div className="hero-panel">
        <span className="eyebrow">Email hygiene without the noise</span>
        <h1>Upload a list, verify it in layers, and export only the addresses you trust.</h1>
        <p className="hero-copy">
          EmailVerifier checks syntax, duplicates, role accounts, disposable domains, MX
          records, catch-all behavior, and live mailbox acceptance while keeping the
          experience simple for your team.
        </p>

        <div className="hero-points">
          <div className="hero-point">
            <strong>7-layer verification</strong>
            <span>From syntax to SMTP probing with fast progress tracking.</span>
          </div>
          <div className="hero-point">
            <strong>Export by outcome</strong>
            <span>Download safe, risky, invalid, or the full annotated list.</span>
          </div>
          <div className="hero-point">
            <strong>No login flow yet</strong>
            <span>Focused on the core upload-to-results experience first.</span>
          </div>
        </div>
      </div>

      <div className="panel upload-panel">
        <div className="panel-header">
          <div>
            <span className="eyebrow">Upload List</span>
            <h2>Drop your file to begin</h2>
          </div>
          <span className="chip chip-highlight">CSV / TXT / XLSX</span>
        </div>

        <div
          className={`dropzone ${dropzone.isDragActive ? "dropzone-active" : ""}`}
          {...dropzone.getRootProps()}
        >
          <input {...dropzone.getInputProps()} />
          <div className="dropzone-illustration">
            <div className="dropzone-orbit" />
            <div className="dropzone-icon">+</div>
          </div>
          <h3>{dropzone.isDragActive ? "Release to upload" : "Drag and drop your list"}</h3>
          <p>
            or <span className="text-link">browse files</span> from your device
          </p>
        </div>

        <div className="panel-meta">
          <div className="meta-row">
            <span>Selected file</span>
            <strong>{fileInfo?.fileName || "None yet"}</strong>
          </div>
          <div className="meta-row">
            <span>Detected rows</span>
            <strong>
              {isReadingFile ? "Counting..." : fileInfo ? fileInfo.rowCount.toLocaleString() : "--"}
            </strong>
          </div>
        </div>

        {errorMessage ? <p className="inline-error">{errorMessage}</p> : null}

        <button
          className="primary-button"
          disabled={!selectedFile || isReadingFile || isSubmitting}
          onClick={handleStartVerification}
          type="button"
        >
          {isSubmitting ? "Starting..." : "Start Verification"}
        </button>
      </div>
    </section>
  );
}
