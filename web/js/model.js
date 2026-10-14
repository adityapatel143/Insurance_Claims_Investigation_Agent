// Pure helpers shared by the UI and unit tests (no DOM access).

export const CLAIM_TYPES = ["AUTO", "PROPERTY", "TRAVEL"];
export const DOCUMENT_TYPES = ["CLAIM_FORM", "INVOICE", "REPAIR_ESTIMATE", "INCIDENT_REPORT", "CORRESPONDENCE", "OTHER"];
export const CONTENT_TYPES = ["text/plain", "text/csv", "application/json"];
export const TERMINAL_STATUSES = ["COMPLETED", "REVIEW_REQUIRED", "FAILED"];
export const CLAIM_ID_PATTERN = /^[A-Z0-9][A-Z0-9-]{3,63}$/;
export const POLICY_PATTERN = /^[A-Z0-9][A-Z0-9-]{3,31}$/;
export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Map a local file name onto the API's FileName pattern ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$. */
export function safeFileName(name) {
  const cleaned = String(name).replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^[^A-Za-z0-9]+/, "");
  return (cleaned || "document.txt").slice(0, 128);
}

export function guessContentType(name) {
  const lower = String(name).toLowerCase();
  if (lower.endsWith(".csv")) return "text/csv";
  if (lower.endsWith(".json")) return "application/json";
  return "text/plain";
}

export function generateClaimId(prefix = "CLM-SYN-WEB") {
  const bytes = crypto.getRandomValues(new Uint8Array(3));
  return `${prefix}-${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("").toUpperCase()}`;
}

/**
 * Accept `aws configure export-credentials --format process` JSON or plain fields.
 * Returns { accessKeyId, secretAccessKey, sessionToken, expiration } or throws.
 */
export function parseCredentials(input) {
  const source = typeof input === "string" ? JSON.parse(input) : input;
  const credentials = {
    accessKeyId: String(source.AccessKeyId ?? source.accessKeyId ?? "").trim(),
    secretAccessKey: String(source.SecretAccessKey ?? source.secretAccessKey ?? "").trim(),
    sessionToken: String(source.SessionToken ?? source.sessionToken ?? "").trim() || undefined,
    expiration: source.Expiration ?? source.expiration ?? undefined,
  };
  if (!/^(AKIA|ASIA)[A-Z0-9]{12,124}$/.test(credentials.accessKeyId)) throw new Error("Access key ID looks invalid");
  if (credentials.secretAccessKey.length < 16) throw new Error("Secret access key looks invalid");
  if (credentials.expiration && Number.isNaN(new Date(credentials.expiration).getTime())) {
    throw new Error("Expiration is not a valid timestamp");
  }
  return credentials;
}

export function isExpired(credentials, now = new Date()) {
  return Boolean(credentials?.expiration) && new Date(credentials.expiration) <= now;
}

/** Client-side checks mirroring ClaimSubmission; the API remains the authority. */
export function validateClaimForm(form) {
  const errors = [];
  if (!CLAIM_ID_PATTERN.test(form.claim_id)) errors.push("Claim ID: 4-64 chars, A-Z, 0-9, hyphen; must start with a letter or digit.");
  if (!POLICY_PATTERN.test(form.policy_reference)) errors.push("Policy reference: 4-32 chars, A-Z, 0-9, hyphen.");
  if (!CLAIM_TYPES.includes(form.claim_type)) errors.push("Choose a claim type.");
  const today = new Date().toISOString().slice(0, 10);
  if (!form.incident_date || form.incident_date > today) errors.push("Incident date is required and cannot be in the future.");
  if (!form.reported_date || form.reported_date > today) errors.push("Reported date is required and cannot be in the future.");
  if (!/^\d{1,10}(\.\d{1,2})?$/.test(form.claimed_amount) || Number(form.claimed_amount) <= 0) {
    errors.push("Claimed amount must be a positive number with at most 2 decimals.");
  }
  if (!/^[A-Z]{3}$/.test(form.currency)) errors.push("Currency must be a 3-letter ISO code.");
  if (!form.incident_description || form.incident_description.length > 4000) errors.push("Description is required (max 4000 characters).");
  if (!form.documents.length) errors.push("Attach at least one document.");
  if (form.documents.length > 20) errors.push("At most 20 documents per claim.");
  return errors;
}
