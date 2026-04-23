import axios from "axios";

function normalizeBaseUrl(url) {
  if (!url) {
    return "";
  }

  return url.endsWith("/") ? url.slice(0, -1) : url;
}

const API_BASE_URL = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL || "");
const DEFAULT_HEADERS = {};

if (import.meta.env.VITE_USER_ID) {
  DEFAULT_HEADERS["X-User-Id"] = import.meta.env.VITE_USER_ID;
}

if (import.meta.env.VITE_API_KEY) {
  DEFAULT_HEADERS["X-API-Key"] = import.meta.env.VITE_API_KEY;
}

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: DEFAULT_HEADERS,
});

export async function uploadVerificationFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await api.post("/api/upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });

  return response.data;
}

export async function fetchJobProgress(jobId) {
  const response = await api.get("/api/progress", {
    params: { job_id: jobId },
  });

  return response.data;
}

export async function cancelJob(jobId) {
  await api.post("/api/cancel", null, {
    params: { job_id: jobId },
  });
}

export function buildDownloadUrl(jobId, type) {
  const params = new URLSearchParams({
    job_id: jobId,
    type,
  });

  if (!API_BASE_URL) {
    return `/api/download?${params.toString()}`;
  }

  return `${API_BASE_URL}/api/download?${params.toString()}`;
}
