// Signed calls to the claims HTTP API and presigned S3 uploads.
import { signRequest } from "./sigv4.js";

export class ApiError extends Error {
  constructor(status, body, correlationId) {
    super(body?.message || `HTTP ${status}`);
    this.status = status;
    this.code = body?.code || "HTTP_ERROR";
    this.details = Array.isArray(body?.details) ? body.details : [];
    this.correlationId = body?.correlation_id || correlationId || null;
  }
}

export function randomUuid() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function regionFromEndpoint(endpoint) {
  const match = /^[a-z0-9]+\.execute-api\.([a-z0-9-]+)\.amazonaws\.com$/.exec(new URL(endpoint).host);
  if (!match) throw new Error("API endpoint must look like https://<id>.execute-api.<region>.amazonaws.com");
  return match[1];
}

export class ApiClient {
  constructor(endpoint, credentials) {
    const url = new URL(endpoint);
    if (url.protocol !== "https:") throw new Error("API endpoint must use https");
    this.endpoint = url.origin;
    this.region = regionFromEndpoint(endpoint);
    this.credentials = credentials;
  }

  async call(method, path, payload) {
    const url = `${this.endpoint}${path}`;
    const body = payload === undefined ? "" : JSON.stringify(payload);
    const headers = { "x-correlation-id": `web-${randomUuid()}` };
    if (body) headers["content-type"] = "application/json";
    const signed = signRequest({
      method, url, headers, body, region: this.region, service: "execute-api", credentials: this.credentials,
    });
    const response = await fetch(url, {
      method, headers: signed, body: body || undefined, mode: "cors", credentials: "omit", cache: "no-store",
    });
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { message: text.slice(0, 300) };
    }
    if (!response.ok) throw new ApiError(response.status, data, headers["x-correlation-id"]);
    return data;
  }

  requestUpload(claimId, fileName, contentType) {
    return this.call("POST", "/uploads", { claim_id: claimId, file_name: fileName, content_type: contentType });
  }

  submitClaim(submission) {
    return this.call("POST", "/claims", submission);
  }

  getStatus(claimId, jobId) {
    return this.call("GET", `/claims/${encodeURIComponent(claimId)}/jobs/${encodeURIComponent(jobId)}`);
  }
}

export async function uploadPresigned(upload, blob) {
  const url = new URL(upload.upload_url);
  if (url.protocol !== "https:") throw new Error("Refusing non-HTTPS upload URL");
  const form = new FormData();
  for (const [name, value] of Object.entries(upload.upload_fields)) form.append(name, value);
  form.append("file", blob);
  const response = await fetch(url, { method: "POST", body: form, mode: "cors", credentials: "omit" });
  if (!response.ok) {
    const detail = (await response.text()).match(/<Message>([^<]*)<\/Message>/)?.[1] ?? `HTTP ${response.status}`;
    throw new Error(`Upload failed: ${detail}`);
  }
}

export async function fetchReport(reportUrl) {
  const url = new URL(reportUrl);
  if (url.protocol !== "https:") throw new Error("Refusing non-HTTPS report URL");
  const response = await fetch(url, { mode: "cors", credentials: "omit", cache: "no-store" });
  if (!response.ok) throw new Error(`Report download failed (HTTP ${response.status}); the link may have expired.`);
  return response.json();
}
