import { ApiClient, ApiError, fetchReport, randomUuid, uploadPresigned } from "./api.js";
import { $, clear, el, formatTime, toast } from "./dom.js";
import {
  CLAIM_TYPES, CONTENT_TYPES, DOCUMENT_TYPES, TERMINAL_STATUSES, UUID_PATTERN, CLAIM_ID_PATTERN,
  generateClaimId, guessContentType, isExpired, parseCredentials, safeFileName, validateClaimForm,
} from "./model.js";
import { renderReport } from "./report.js";
import { forgetJobs, recentJobs, rememberJob, saveSettings, settings } from "./store.js";

const POLL_MS = 5000;
const state = { client: null, credentials: null, documents: [], samples: [], pollTimer: null, activeJob: null };

// ---------- navigation ----------
function showTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => {
    const active = tab.dataset.tab === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".panel").forEach((panel) => (panel.hidden = panel.id !== `tab-${name}`));
}

function requireClient() {
  if (!state.client) throw new Error("Connect first (tab 1).");
  if (isExpired(state.credentials)) {
    forgetCredentials();
    throw new Error("Credentials expired. Paste fresh temporary credentials.");
  }
  return state.client;
}

function describeError(error) {
  if (error instanceof ApiError) {
    const details = error.details.length ? ` ${error.details.join(" ")}` : "";
    const ref = error.correlationId ? ` (ref ${error.correlationId})` : "";
    if (error.status === 403) return `Access denied: the credentials need execute-api:Invoke on this API.${ref}`;
    return `${error.code}: ${error.message}.${details}${ref}`;
  }
  if (error instanceof TypeError) {
    return "Network or CORS error. Check the endpoint, and that this site's origin is in web_allowed_origins.";
  }
  return error.message || String(error);
}

// ---------- connect ----------
function setConnected(connected, text) {
  const pill = $("#connection-pill");
  pill.className = `pill ${connected ? "pill-on" : "pill-off"}`;
  pill.textContent = text;
}

function forgetCredentials() {
  state.client = null;
  state.credentials = null;
  $("#credentials-json").value = "";
  setConnected(false, "Not connected");
  $("#connect-status").textContent = "Credentials cleared from memory.";
}

function onConnect(event) {
  event.preventDefault();
  try {
    const endpoint = $("#api-endpoint").value.trim().replace(/\/+$/, "");
    const credentials = parseCredentials($("#credentials-json").value);
    if (isExpired(credentials)) throw new Error("These credentials have already expired.");
    state.client = new ApiClient(endpoint, credentials);
    state.credentials = credentials;
    $("#credentials-json").value = "";
    saveSettings({ apiEndpoint: endpoint });
    const expiry = credentials.expiration ? `, expires ${formatTime(credentials.expiration)}` : "";
    setConnected(true, `Connected (${state.client.region})`);
    $("#connect-status").textContent = `Ready: ${credentials.accessKeyId.slice(0, 4)}...${credentials.accessKeyId.slice(-4)}${expiry}.`;
    if (!credentials.sessionToken) toast("Long-term access keys detected. Prefer temporary credentials.", "error");
    toast("Connected. Credentials are held in memory only.");
    showTab("submit");
  } catch (error) {
    $("#connect-status").textContent = `Not connected: ${error.message}`;
    toast(error.message, "error");
  }
}

// ---------- documents ----------
function renderDocuments() {
  const body = clear($("#documents"));
  if (!state.documents.length) {
    body.append(el("tr", {}, el("td", { colspan: 5, class: "muted" }, "No documents attached.")));
    return;
  }
  state.documents.forEach((doc, index) => {
    const select = (options, value, key) =>
      el("select", { onchange: (e) => (doc[key] = e.target.value) }, options.map((o) => el("option", { value: o, selected: o === value }, o)));
    body.append(
      el(
        "tr",
        {},
        el("td", {}, el("code", {}, doc.fileName)),
        el("td", {}, `${(doc.blob.size / 1024).toFixed(1)} KB`),
        el("td", {}, select(DOCUMENT_TYPES, doc.documentType, "documentType")),
        el("td", {}, select(CONTENT_TYPES, doc.contentType, "contentType")),
        el("td", {}, el("button", { type: "button", class: "link", onclick: () => { state.documents.splice(index, 1); renderDocuments(); } }, "Remove")),
      ),
    );
  });
}

function addFiles(files) {
  for (const file of files) {
    state.documents.push({
      fileName: safeFileName(file.name),
      blob: file,
      documentType: state.documents.length ? "OTHER" : "CLAIM_FORM",
      contentType: guessContentType(file.name),
    });
  }
  renderDocuments();
}

// ---------- samples ----------
async function loadSampleIndex() {
  const select = $("#sample-select");
  try {
    const response = await fetch("samples/index.json", { cache: "no-store" });
    state.samples = response.ok ? await response.json() : [];
  } catch {
    state.samples = [];
  }
  clear(select).append(
    el("option", { value: "" }, state.samples.length ? "Choose a scenario..." : "No samples available"),
    ...state.samples.map((s) => el("option", { value: s.scenario }, s.scenario)),
  );
}

async function loadSample() {
  const sample = state.samples.find((s) => s.scenario === $("#sample-select").value);
  if (!sample) return toast("Choose a sample scenario first.", "error");
  try {
    const manifest = await (await fetch(sample.path, { cache: "no-store" })).json();
    const base = sample.path.replace(/claim\.json$/, "");
    const form = $("#claim-form");
    form.claim_id.value = generateClaimId(manifest.claim_id_prefix);
    for (const field of ["policy_reference", "claim_type", "incident_date", "reported_date", "claimed_amount", "currency", "incident_description"]) {
      form[field].value = manifest[field];
    }
    state.documents = await Promise.all(
      manifest.documents.map(async (doc) => {
        const response = await fetch(`${base}${encodeURIComponent(doc.file)}`, { cache: "no-store" });
        if (!response.ok) throw new Error(`Sample file ${doc.file} is missing`);
        const blob = await response.blob();
        return { fileName: safeFileName(doc.file), blob, documentType: doc.document_type, contentType: doc.content_type };
      }),
    );
    renderDocuments();
    toast(`Loaded synthetic scenario "${sample.scenario}".`);
  } catch (error) {
    toast(`Could not load sample: ${error.message}`, "error");
  }
}

// ---------- submit ----------
function progressStep(text) {
  const item = el("li", { class: "step running" }, text);
  $("#progress").append(item);
  return {
    done: (suffix = "") => { item.className = "step done"; item.textContent = `${text} ${suffix}`.trim(); },
    fail: (message) => { item.className = "step failed"; item.textContent = `${text} - ${message}`; },
  };
}

async function onSubmitClaim(event) {
  event.preventDefault();
  const form = event.target;
  const values = Object.fromEntries(new FormData(form).entries());
  values.claim_id = String(values.claim_id || "").trim().toUpperCase();
  values.policy_reference = String(values.policy_reference || "").trim().toUpperCase();
  values.currency = String(values.currency || "").trim().toUpperCase();
  values.claimed_amount = String(values.claimed_amount || "").trim();
  values.documents = state.documents;

  const errors = validateClaimForm(values);
  const errorList = clear($("#form-errors"));
  errorList.hidden = !errors.length;
  errors.forEach((message) => errorList.append(el("li", {}, message)));
  if (errors.length) return;

  let client;
  try {
    client = requireClient();
  } catch (error) {
    return toast(error.message, "error");
  }

  const button = $("#submit-claim");
  button.disabled = true;
  clear($("#progress"));
  let step = null;
  try {
    const references = [];
    for (const doc of state.documents) {
      step = progressStep(`Uploading ${doc.fileName}`);
      const upload = await client.requestUpload(values.claim_id, doc.fileName, doc.contentType);
      await uploadPresigned(upload, doc.blob);
      references.push({
        document_id: upload.document_id,
        object_key: upload.object_key,
        document_type: doc.documentType,
        content_type: upload.content_type,
      });
      step.done("ok");
    }
    step = progressStep("Submitting claim for investigation");
    const accepted = await client.submitClaim({
      client_request_id: randomUuid(),
      claim_id: values.claim_id,
      policy_reference: values.policy_reference,
      claim_type: values.claim_type,
      incident_date: values.incident_date,
      reported_date: values.reported_date,
      claimed_amount: values.claimed_amount,
      currency: values.currency,
      incident_description: String(values.incident_description).trim(),
      documents: references,
    });
    step.done(`- job ${accepted.job_id} ${accepted.status}`);
    rememberJob({ claim_id: accepted.claim_id, job_id: accepted.job_id, status: accepted.status, submitted_at: new Date().toISOString() });
    toast("Claim accepted. Investigation runs asynchronously.");
    state.documents = [];
    renderDocuments();
    showTab("jobs");
    openJob(accepted.claim_id, accepted.job_id);
  } catch (error) {
    step?.fail(describeError(error));
    toast(describeError(error), "error");
  } finally {
    button.disabled = false;
  }
}

// ---------- jobs ----------
function renderRecentJobs() {
  const body = clear($("#recent-jobs"));
  const jobs = recentJobs();
  if (!jobs.length) {
    body.append(el("tr", {}, el("td", { colspan: 3, class: "muted" }, "No jobs submitted from this browser yet.")));
    return;
  }
  for (const job of jobs) {
    body.append(
      el(
        "tr",
        { class: state.activeJob?.job_id === job.job_id ? "selected" : null, tabindex: 0, onclick: () => openJob(job.claim_id, job.job_id), onkeydown: (e) => e.key === "Enter" && openJob(job.claim_id, job.job_id) },
        el("td", {}, el("code", {}, job.claim_id)),
        el("td", {}, el("span", { class: `status status-${job.status}` }, job.status ?? "-")),
        el("td", {}, formatTime(job.submitted_at)),
      ),
    );
  }
}

function stopPolling() {
  clearTimeout(state.pollTimer);
  state.pollTimer = null;
}

function renderJobDetail(job, error) {
  const panel = clear($("#job-detail"));
  const terminal = TERMINAL_STATUSES.includes(job?.status);
  panel.append(
    el("div", { class: "card-title" }, el("h3", {}, "Job"), el("button", { type: "button", class: "secondary small", onclick: () => refreshJob(true) }, "Refresh")),
  );
  if (error) panel.append(el("p", { class: "error-text" }, error));
  if (!job) return;
  panel.append(
    el(
      "dl",
      { class: "facts" },
      el("dt", {}, "Status"), el("dd", {}, el("span", { class: `status status-${job.status}` }, job.status), terminal ? null : el("span", { class: "spinner", "aria-label": "polling" })),
      el("dt", {}, "Claim"), el("dd", {}, el("code", {}, job.claim_id)),
      el("dt", {}, "Job"), el("dd", {}, el("code", {}, job.job_id)),
      el("dt", {}, "Correlation"), el("dd", {}, el("code", {}, job.correlation_id)),
      el("dt", {}, "Created"), el("dd", {}, formatTime(job.created_at)),
      el("dt", {}, "Dispatched"), el("dd", {}, formatTime(job.dispatched_at)),
      el("dt", {}, "Completed"), el("dd", {}, formatTime(job.completed_at)),
      job.failure_category ? [el("dt", {}, "Failure"), el("dd", {}, job.failure_category)] : null,
      job.human_review_required === true ? [el("dt", {}, "Review"), el("dd", {}, "Human review required")] : null,
    ),
  );
  if (job.report_url) {
    const reportHost = el("div", { class: "report-host" });
    panel.append(
      el(
        "div",
        { class: "actions" },
        el("button", { type: "button", class: "primary", onclick: () => showReport(job.report_url, reportHost) }, "View report"),
        el("a", { class: "button secondary", href: job.report_url, target: "_blank", rel: "noopener noreferrer" }, "Download JSON"),
        el("span", { class: "muted small" }, `Link expires ${formatTime(job.report_url_expires_at)}`),
      ),
      reportHost,
    );
  } else if (job.report_location) {
    panel.append(el("p", { class: "muted" }, "A report exists, but only the submitting identity can download it."));
  } else if (!terminal) {
    panel.append(el("p", { class: "muted" }, `Investigation in progress; refreshing every ${POLL_MS / 1000}s.`));
  }
}

async function showReport(url, host) {
  clear(host).append(el("p", { class: "muted" }, "Loading report..."));
  try {
    clear(host).append(renderReport(await fetchReport(url)));
  } catch (error) {
    clear(host).append(el("p", { class: "error-text" }, describeError(error)));
  }
}

async function refreshJob(manual = false) {
  stopPolling();
  const target = state.activeJob;
  if (!target) return;
  try {
    const job = await requireClient().getStatus(target.claim_id, target.job_id);
    if (state.activeJob !== target) return;
    rememberJob({ claim_id: job.claim_id, job_id: job.job_id, status: job.status });
    renderRecentJobs();
    renderJobDetail(job);
    if (!TERMINAL_STATUSES.includes(job.status)) state.pollTimer = setTimeout(refreshJob, POLL_MS);
  } catch (error) {
    renderJobDetail(null, describeError(error));
    if (manual) toast(describeError(error), "error");
  }
}

function openJob(claimId, jobId) {
  state.activeJob = { claim_id: claimId, job_id: jobId };
  renderRecentJobs();
  clear($("#job-detail")).append(el("p", { class: "muted" }, "Loading..."));
  refreshJob(true);
}

function onLookup(event) {
  event.preventDefault();
  const claimId = event.target.claim_id.value.trim().toUpperCase();
  const jobId = event.target.job_id.value.trim().toLowerCase();
  if (!CLAIM_ID_PATTERN.test(claimId) || !UUID_PATTERN.test(jobId)) {
    return toast("Enter a valid claim ID and job ID (UUID).", "error");
  }
  openJob(claimId, jobId);
}

// ---------- init ----------
async function loadConfig() {
  const saved = settings().apiEndpoint;
  let configured = "";
  try {
    const response = await fetch("config.json", { cache: "no-store" });
    if (response.ok) configured = (await response.json()).apiEndpoint || "";
  } catch {
    configured = "";
  }
  $("#api-endpoint").value = saved || configured;
}

function init() {
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
  $("#http-warning").hidden = location.protocol !== "http:" || local;

  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => showTab(tab.dataset.tab)));
  $("#connect-form").addEventListener("submit", onConnect);
  $("#forget-credentials").addEventListener("click", forgetCredentials);
  $("#claim-form").addEventListener("submit", onSubmitClaim);
  $("#file-input").addEventListener("change", (e) => { addFiles(e.target.files); e.target.value = ""; });
  $("#new-claim-id").addEventListener("click", () => ($("#claim-form").claim_id.value = generateClaimId()));
  $("#load-sample").addEventListener("click", loadSample);
  $("#lookup-form").addEventListener("submit", onLookup);
  $("#clear-jobs").addEventListener("click", () => { forgetJobs(); renderRecentJobs(); });

  const claimType = $("#claim-form").claim_type;
  CLAIM_TYPES.forEach((type) => claimType.append(el("option", { value: type }, type)));
  $("#claim-form").claim_id.value = generateClaimId();

  renderDocuments();
  renderRecentJobs();
  loadConfig();
  loadSampleIndex();
}

init();
