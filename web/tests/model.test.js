import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { test } from "node:test";

import { regionFromEndpoint } from "../js/api.js";
import { generateClaimId, guessContentType, isExpired, parseCredentials, safeFileName, validateClaimForm } from "../js/model.js";
import { amzDate } from "../js/sigv4.js";

// Node 18 has no global `crypto`; browsers do.
globalThis.crypto ??= webcrypto;

const validForm = () => ({
  claim_id: "CLM-SYN-AUTO-1A2B3C",
  policy_reference: "POL-SYN-2001",
  claim_type: "AUTO",
  incident_date: "2026-08-14",
  reported_date: "2026-08-16",
  claimed_amount: "2480.00",
  currency: "USD",
  incident_description: "SYNTHETIC: rear bumper damage.",
  documents: [{}],
});

test("safeFileName maps names onto the API pattern", () => {
  assert.equal(safeFileName("My Claim (1).txt"), "My-Claim-1-.txt");
  assert.equal(safeFileName("..hidden.csv"), "hidden.csv");
  assert.equal(safeFileName("???"), "document.txt");
  assert.equal(safeFileName("a".repeat(300)).length, 128);
  assert.match(safeFileName("résumé.json"), /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/);
});

test("guessContentType", () => {
  assert.equal(guessContentType("x.CSV"), "text/csv");
  assert.equal(guessContentType("x.json"), "application/json");
  assert.equal(guessContentType("x.txt"), "text/plain");
});

test("generateClaimId matches the ClaimId pattern", () => {
  assert.match(generateClaimId(), /^[A-Z0-9][A-Z0-9-]{3,63}$/);
  assert.match(generateClaimId("CLM-SYN-TRVL"), /^CLM-SYN-TRVL-[0-9A-F]{6}$/);
});

test("parseCredentials accepts export-credentials process JSON", () => {
  const fakeKeyId = "ASIAEXAMPLEEXAMPLE00"; // pragma: allowlist secret
  const parsed = parseCredentials(
    JSON.stringify({ Version: 1, AccessKeyId: fakeKeyId, SecretAccessKey: "x".repeat(40), SessionToken: "tok", Expiration: "2030-01-01T00:00:00Z" }),
  );
  assert.equal(parsed.accessKeyId, fakeKeyId);
  assert.equal(parsed.sessionToken, "tok");
  assert.equal(isExpired(parsed, new Date("2029-12-31T00:00:00Z")), false);
  assert.equal(isExpired(parsed, new Date("2030-01-02T00:00:00Z")), true);
});

test("parseCredentials rejects malformed input", () => {
  assert.throws(() => parseCredentials("not json"));
  assert.throws(() => parseCredentials({ AccessKeyId: "nope", SecretAccessKey: "x".repeat(40) }), /Access key/);
  assert.throws(() => parseCredentials({ AccessKeyId: "ASIA" + "0".repeat(16), SecretAccessKey: "short" }), /Secret/);
});

test("validateClaimForm mirrors API constraints", () => {
  assert.deepEqual(validateClaimForm(validForm()), []);
  assert.equal(validateClaimForm({ ...validForm(), claim_id: "x" }).length, 1);
  assert.equal(validateClaimForm({ ...validForm(), claimed_amount: "12.345" }).length, 1);
  assert.equal(validateClaimForm({ ...validForm(), incident_date: "2999-01-01" }).length, 1);
  assert.equal(validateClaimForm({ ...validForm(), documents: [] }).length, 1);
});

test("regionFromEndpoint and amzDate", () => {
  assert.equal(regionFromEndpoint("https://abc123.execute-api.eu-west-2.amazonaws.com"), "eu-west-2");
  assert.throws(() => regionFromEndpoint("https://example.com"));
  assert.equal(amzDate(new Date("2026-10-01T12:34:56.789Z")), "20261001T123456Z");
});
