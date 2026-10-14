// Browser-local state. Only identifiers and non-secret settings are persisted; never credentials.

const JOBS_KEY = "claims-web.recent-jobs";
const SETTINGS_KEY = "claims-web.settings";
const MAX_JOBS = 25;

function read(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

export function recentJobs() {
  const jobs = read(JOBS_KEY, []);
  return Array.isArray(jobs) ? jobs : [];
}

export function rememberJob(job) {
  const others = recentJobs().filter((j) => j.job_id !== job.job_id);
  const merged = { ...recentJobs().find((j) => j.job_id === job.job_id), ...job };
  localStorage.setItem(JOBS_KEY, JSON.stringify([merged, ...others].slice(0, MAX_JOBS)));
}

export function forgetJobs() {
  localStorage.removeItem(JOBS_KEY);
}

export function settings() {
  return read(SETTINGS_KEY, {});
}

export function saveSettings(values) {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...settings(), ...values }));
}
