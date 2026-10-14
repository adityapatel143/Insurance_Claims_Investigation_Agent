# User guide: web app

This guide explains how an analyst uses the web app to submit a claim, follow the investigation, and read
the advisory report. For deployment, see [README section 6](../README.md#6-web-app-on-s3-optional).

> All output is advisory. The assistant never approves, rejects, prices, or pays a claim and never labels
> anyone as fraudulent. Use **synthetic data only**.

## Contents

1. [Before you start](#1-before-you-start)
2. [Get temporary credentials](#2-get-temporary-credentials)
3. [Connect](#3-connect)
4. [Submit a claim](#4-submit-a-claim)
5. [Follow the job](#5-follow-the-job)
6. [Read the report](#6-read-the-report)
7. [Troubleshooting](#7-troubleshooting)
8. [Privacy and security notes](#8-privacy-and-security-notes)

## 1. Before you start

You need:

| Item | Where it comes from |
|---|---|
| Web app URL | Your administrator (web stack output `website_url`, for example `http://<bucket>.s3-website-<region>.amazonaws.com`) |
| API endpoint | Usually prefilled; otherwise the platform output `api_endpoint` (`https://<id>.execute-api.<region>.amazonaws.com`) |
| AWS identity allowed to call the API | An IAM role or user with `execute-api:Invoke` on the API (README section 5) |
| AWS CLI v2 | To export temporary credentials on your machine |

Use a current desktop browser (Chrome, Edge, Firefox, or Safari).

## 2. Get temporary credentials

The API uses AWS IAM authentication, so the page signs each request with your AWS credentials. Use
**temporary** credentials from a role that can only call this API.

1. Configure a profile for that role once, for example in `~/.aws/config`:

   ```ini
   [profile claims-analyst]
   role_arn = arn:aws:iam::111122223333:role/claims-analyst
   source_profile = default
   region = us-east-1
   ```

   With IAM Identity Center, `aws configure sso --profile claims-analyst` is enough.

2. Export the credentials as JSON:

   ```bash
   aws configure export-credentials --profile claims-analyst --format process
   ```

   The output looks like this (values shortened):

   ```json
   {"Version": 1, "AccessKeyId": "ASIA...", "SecretAccessKey": "...", "SessionToken": "...", "Expiration": "2026-10-01T13:00:00+00:00"}
   ```

Credentials that have no `SessionToken` are long-term access keys; the page accepts them but shows a
warning. Avoid them.

## 3. Connect

1. Open the web app URL. The **1. Connect** tab opens.
2. Check the **API endpoint** (it is remembered in this browser after the first successful connect).
3. Paste the whole JSON from step 2 into **Temporary credentials (JSON)**.
4. Choose **Connect**.

The header pill changes to **Connected (&lt;region&gt;)** and the status line shows the masked key ID and the
expiry time. The credentials field is cleared immediately; the credentials stay only in this tab's memory.

- **Forget credentials** removes them from memory at once.
- Reloading or closing the tab also forgets them; connect again with fresh credentials.
- When the credentials expire, the next action asks you to paste new ones.

A yellow banner appears when the page is served over plain HTTP. See
[Privacy and security notes](#8-privacy-and-security-notes).

## 4. Submit a claim

Open **2. New claim**.

### Option A: load a synthetic sample

1. Pick a scenario in **Synthetic sample scenario**:
   - `complete`: all expected documents, consistent facts.
   - `missing-documents`: a required document is absent.
   - `inconsistent`: amounts or dates differ between the form and a document, and the claim was reported late.
2. Choose **Load sample**. The form and the document list are filled in, with a new unique claim ID.

### Option B: enter a claim manually

| Field | Rules |
|---|---|
| Claim ID | 4-64 characters: `A-Z`, `0-9`, `-`; starts with a letter or digit. **Generate** creates one (`CLM-SYN-WEB-xxxxxx`). |
| Policy reference | 4-32 characters: `A-Z`, `0-9`, `-` (for example `POL-SYN-1001`). |
| Claim type | `AUTO`, `PROPERTY`, or `TRAVEL`. |
| Incident date, Reported date | Not in the future. |
| Claimed amount | Positive, at most 2 decimals (for example `1250.00`). |
| Currency | 3-letter ISO code (for example `USD`). |
| Incident description | Required, up to 4000 characters. Mark synthetic text as such. |

Lowercase letters in IDs and the currency are converted to uppercase on submit.

### Documents

1. Choose **Add documents** and select one or more files.
2. For each file, set the **Document type** (`CLAIM_FORM`, `INVOICE`, `REPAIR_ESTIMATE`, `INCIDENT_REPORT`,
   `CORRESPONDENCE`, `OTHER`) and check the **Content type**.
3. Use **Remove** to drop a file.

Supported formats: plain text (`.txt`, best as `Key: Value` lines), CSV (`field,value` rows or a header row
plus one data row), and JSON objects. Other formats are not read. At most 20 documents per claim; the size
limit per file is set by the deployment (10 MiB in the default configuration). File names are adjusted
automatically to the allowed characters (letters, digits, `.`, `_`, `-`).

The required documents differ by claim type; anything missing is reported as missing information.

### Submit

Choose **Upload and submit**. The progress list shows each step:

1. `Uploading <file> ok`, once per document (each file goes directly to S3 through a short-lived upload link);
2. `Submitting claim for investigation - job <job_id> QUEUED`.

If the form has problems, they are listed in red above the button and nothing is sent. After a successful
submit the app switches to **3. Jobs & reports** and opens the new job.

## 5. Follow the job

The **3. Jobs & reports** tab has two parts:

- **Recent jobs (this browser):** jobs submitted or looked up here, newest first. Select a row to open it.
  **Clear** empties the list (it only stores claim IDs, job IDs, status, and time).
- **Check status:** enter a claim ID and job ID (for example from a colleague or a script) to open any job
  you are allowed to see.

The job panel shows status, claim, job, correlation ID, and timestamps. While the job is running it
refreshes every 5 seconds (spinner next to the status); **Refresh** reloads it immediately.

| Status | Meaning | What to do |
|---|---|---|
| `QUEUED` | Accepted and waiting to start. | Wait. If it stays queued for a long time, tell your administrator (the agent runtime may not be deployed). |
| `PROCESSING` | The investigation is running. | Wait. |
| `COMPLETED` | Finished; nothing required review. | Read the report and continue with normal handling. |
| `REVIEW_REQUIRED` | Finished; at least one reason requires human review. | Read the review reasons and the report. |
| `FAILED` | Did not finish. The **Failure** field shows why (for example `TIMEOUT`, `DISPATCH_EXHAUSTED`). | Resubmit with a new claim ID, or give the correlation ID to support. |

## 6. Read the report

When the job is `COMPLETED` or `REVIEW_REQUIRED`:

- **View report** shows the report on the page.
- **Download JSON** saves the full report.
- The link expires after a few minutes (the expiry time is shown). Choose **Refresh** to get a new link.

Only the identity that **submitted** the claim gets the report link. Others see
"A report exists, but only the submitting identity can download it."

Report sections:

| Section | How to use it |
|---|---|
| Header | Status, overall confidence, and whether human review is required. |
| Executive summary | A short, neutral description of the claim as submitted. |
| Review reasons | Why the case was routed to review (for example `ANOMALY_SIGNAL`, `MISSING_INFORMATION`, `LOW_CONFIDENCE`). |
| Potential anomaly signals | Inconsistencies worth checking, each with origin (`RULE` or `MODEL`), confidence, evidence references, and limitations. They are prompts for review, not conclusions. |
| Risk indicators | Category and level (`LOW`, `MEDIUM`, `HIGH`) with rationale and evidence. |
| Missing information | Expected items that were not provided, with the reason. |
| Recommended analyst actions | Suggested next steps (for example requesting a document), with priority. |
| Evidence | The items cited above: `doc:<document>#L<line>` points to a line in an uploaded document; `meta:<field>` points to a submitted field. |
| Retrieved guidance and examples | Internal guidance and similar synthetic past cases used as context (`src:` references). |
| Limitations | Known limits of this particular analysis. |

Always check the cited evidence before acting on a finding. Decisions remain with you and your claims system.

## 7. Troubleshooting

| Message | Cause and fix |
|---|---|
| `Not connected: Access key ID looks invalid` / `Secret access key looks invalid` | The pasted text is incomplete. Paste the full JSON from `export-credentials`. |
| `These credentials have already expired.` / `Credentials expired...` | Export fresh credentials and connect again. |
| `API endpoint must look like https://<id>.execute-api.<region>.amazonaws.com` | Correct the endpoint (no path, `https` only). |
| `Connect first (tab 1).` | Connect before submitting or checking status. |
| `Access denied: the credentials need execute-api:Invoke on this API.` | Your role cannot call this API; ask your administrator for access. |
| `Network or CORS error...` | Wrong endpoint, no network, or this site's address is not allowed by the API (`web_allowed_origins`). Tell your administrator the page URL. |
| `Upload failed: ...` | The file is larger than allowed or its content type does not match; check the file and the Content type column. |
| `VALIDATION_ERROR: ...`, `IDEMPOTENCY_CONFLICT: ...`, or other `CODE: message (ref ...)` | The API rejected the request; the details say which field. Keep the `ref` (correlation ID) for support. |
| `DOCUMENT_REJECTED` | An uploaded object was missing, too large, or of a different type than declared; it was moved to quarantine. Upload it again. |
| `Report download failed ... may have expired` | Choose **Refresh** to get a new link. |
| No samples in the list | The deployment did not include the samples; ask your administrator to redeploy with `scripts/sh/web_deploy.sh`. |

## 8. Privacy and security notes

- Credentials are kept only in the open tab's memory; they are never saved in the browser or sent anywhere
  except as request signatures to the API.
- The browser's local storage keeps only the API endpoint and the IDs and status of recent jobs.
- The default S3 website is served over **plain HTTP**. Someone who can tamper with your network could
  change the page. Use short-lived credentials limited to `execute-api:Invoke`, use trusted networks, and
  choose **Forget credentials** when you are done.
- Upload and report links are short-lived and signed; report links are issued only to the submitter.
- Enter synthetic data only. Do not paste real names, policy numbers, or personal details.
