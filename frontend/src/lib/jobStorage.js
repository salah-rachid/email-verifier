const STORAGE_KEY = "emailverifier.jobs";

export function saveJobMeta(meta) {
  const current = readStorage();
  current[meta.jobId] = {
    ...(current[meta.jobId] || {}),
    ...meta,
    updatedAt: new Date().toISOString(),
  };
  writeStorage(current);
}

export function getJobMeta(jobId) {
  const current = readStorage();
  return current[jobId] || null;
}

function readStorage() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function writeStorage(value) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}
