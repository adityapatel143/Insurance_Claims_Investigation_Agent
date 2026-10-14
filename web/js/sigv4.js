// AWS Signature Version 4 for API Gateway (`execute-api`) requests made from the browser.
import { hmacSha256, sha256, toHex, utf8 } from "./sha256.js";

const encodeRfc3986 = (value) =>
  encodeURIComponent(value).replace(/[!'()*]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);

export function amzDate(date = new Date()) {
  return date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

// Non-S3 services encode the (already URL-encoded) path once more, matching botocore.
function canonicalPath(pathname) {
  return pathname.split("/").map(encodeRfc3986).join("/") || "/";
}

function canonicalQuery(searchParams) {
  return [...searchParams.entries()]
    .map(([k, v]) => [encodeRfc3986(k), encodeRfc3986(v)])
    .sort(([ak, av], [bk, bv]) => (ak === bk ? (av < bv ? -1 : 1) : ak < bk ? -1 : 1))
    .map(([k, v]) => `${k}=${v}`)
    .join("&");
}

/**
 * Return the headers to send (without `host`, which the browser sets) including `authorization`.
 * `credentials` = { accessKeyId, secretAccessKey, sessionToken? }.
 */
export function signRequest({ method, url, headers = {}, body = "", region, service, credentials, date }) {
  const target = new URL(url);
  const timestamp = date ?? amzDate();
  const day = timestamp.slice(0, 8);

  const signed = {};
  for (const [name, value] of Object.entries(headers)) signed[name.toLowerCase()] = String(value);
  signed.host = target.host;
  signed["x-amz-date"] = timestamp;
  if (credentials.sessionToken) signed["x-amz-security-token"] = credentials.sessionToken;

  const names = Object.keys(signed).sort();
  const canonicalHeaders = names.map((n) => `${n}:${signed[n].trim().replace(/\s+/g, " ")}\n`).join("");
  const signedHeaders = names.join(";");
  const payload = typeof body === "string" ? utf8(body) : body;
  const canonicalRequest = [
    method.toUpperCase(),
    canonicalPath(target.pathname),
    canonicalQuery(target.searchParams),
    canonicalHeaders,
    signedHeaders,
    toHex(sha256(payload)),
  ].join("\n");

  const scope = `${day}/${region}/${service}/aws4_request`;
  const stringToSign = ["AWS4-HMAC-SHA256", timestamp, scope, toHex(sha256(utf8(canonicalRequest)))].join("\n");
  let key = hmacSha256(utf8(`AWS4${credentials.secretAccessKey}`), utf8(day));
  for (const part of [region, service, "aws4_request"]) key = hmacSha256(key, utf8(part));
  const signature = toHex(hmacSha256(key, utf8(stringToSign)));

  const { host: _host, ...toSend } = signed;
  toSend.authorization =
    `AWS4-HMAC-SHA256 Credential=${credentials.accessKeyId}/${scope}, ` +
    `SignedHeaders=${signedHeaders}, Signature=${signature}`;
  return toSend;
}
