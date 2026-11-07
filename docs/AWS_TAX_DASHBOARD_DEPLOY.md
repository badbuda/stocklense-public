# StockLens — Tax layer in AWS + the six-screen portal

**Scope:** research-only tax signal and hypothetical net worth. No frozen
model changes, real broker orders, ST/PROD investment decisions, or AWS live NAV
overwrite. Published static site is NOT an appropriate storage place for
personal broker history, tax lots or private FX evidence.

## Data flow

1. **Historical simulation:** `docs/portal.js` runs the same observed QQQ
   and TQQQ price series twice: existing *pre-tax* cost model, and a separate
   approximate 25% **nominal USD** immediate-sale-tax scenario. It also
   illustrates a full liquidation with exit costs. Neither scenario claims
   Israeli after-tax CAGR. Tax lots, realized sales and buying power are
   modeled independently; QQQ receives the same model.
2. **Public portfolio/paper:** `docs/tax-status.json` is permanently
   fail-closed unless independently verified. The public page NEVER
   publishes an individual account's tax receipts, FX or realized gains.
   Tax status appears in the header, decision signal, Overview, Paper,
   Performance, Simulator, Research and Data Trust.
3. **Private ST tax report:** `research/private_tax_dashboard_export.py`
   reads a byte-identical, SHA-bound ST Paper receipt (full history), dated
   ILS/USD quotes and an explicitly **human-attested** FX source manifest.
   It checks cash/position/close reconciliation, partial lots, fees/slippage
   and outputs an illustrative after-tax **if fully liquidated** report.
   It does not call AWS or the broker.
4. **Private AWS route:** `infra/aws/tax-research-private-readonly-route.yaml`
   adds `GET /v1/tax?date=YYYY-MM-DD` to the existing HTTP API,
   using the existing Cognito JWT authorizer. The Lambda can only read
   `s3://<private-st-bucket>/tax-research/private/*`; validates a SHA-256
   object-metadata fingerprint and the schema/session/receipt hash.
   No anonymous, wildcard, S3 public or broker access.
5. **Portal:** after a verified current Staging S3 paper session is read,
   the browser may request the **same date** tax report over authenticated
   HTTPS; missing route/FX/evidence/lot history -> **NOT CALCULATED**.
   Expired login clears the private result.

## Site deployment (code only)

Merge PR to `main` **only after CI and security review**. Existing Amplify
app `main.d20nvlvzjafg5m.amplifyapp.com` is connected to GitHub main. A
main push should publish `docs/` automatically. The browser smoke workflow
compares the actual deployed SHA-256 of the tax module and status JSON as well
as the existing portal HTML/JS/price data. Successful CI **alone** does not
prove a new Amplify publish; check the browser workflow and Amplify Hosting job.

## One-time private API route (NOT performed automatically)

Use a reviewed CloudFormation change set against your existing API, with
`PortalApiId` and `PortalAuthorizerId` from the read-only journal stack's
outputs, and `PrivateStBucketName` from the **existing private ST bucket**.
Do not use PROD. Review IAM: GET-only to the narrow
`tax-research/private/` prefix; Lambda cannot place trades or write S3.

Example (CloudShell, account owner only, after reviewing exact template):

```bash
aws cloudformation deploy --region eu-central-1 \
  --stack-name stocklens-st-private-tax-read \
  --template-file infra/aws/tax-research-private-readonly-route.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    PortalApiId="$PORTAL_API_ID" \
    PortalAuthorizerId="$PORTAL_JWT_AUTHORIZER_ID" \
    PrivateStBucketName="$VERIFIED_ST_PRIVATE_BUCKET" \
  --no-execute-changeset
```

This is a **change-set preview only**. Independently verify the Cognito
authorizer, API ID, S3 bucket and IAM before executing the reviewed change set.

## Creating a private report (only after real, dated FX is verified)

Supply a complete SHA-verified ST Paper receipt and actual FX per trade date
**and final session**. The FX attestation JSON needs:

```json
{
  "manually_verified": true,
  "fx_data_sha256": "<SHA256-of-sorted-canonical-FX-JSON>",
  "independent_source": "<auditable issuer and dated source reference>",
  "verified_by": "<human reviewer>"
}
```

A checkbox/string is NOT independent source verification. This must reflect
actual human work and support reconciliation with Excellence/broker forms.
Missing/invalid input fails closed.

```bash
python research/private_tax_dashboard_export.py \
  --receipt /tmp/st_paper_receipt.json \
  --receipt-sha "$ACTUAL_VERIFIED_RECEIPT_SHA256" \
  --fx /tmp/verified_ils_usd.json \
  --fx-attestation /tmp/fx-attestation.json \
  --out /tmp/stocklens-private-tax.json
```

Inspect the report; it is research-only and must remain PRIVATE. After
review, an authorized owner can write the exact bytes to the existing
versioned ST bucket with object metadata
`report-sha256=<SHA256-of-report-file-bytes>` and
`tax-research/private/YYYY-MM-DD.json`. Do not commit the output to GitHub.
The endpoint validates SHA but cannot independently know the authenticity of
the FX rates; this distinction must remain visible to investors.

## Known blockers

- Missing independent, date-stamped USD/ILS history and approved lot/tax rules.
- Actual Excellence per-share/minimum commissions and withholding dates unknown.
- Private ST report publication and CloudFormation route not yet deployed.
- Approximate FIFO and FX-indexed tax research is not a legal tax return.
- Full historical 2010–2026 **Israeli after-tax** CAGR requires independently
  verified execution/FX, corporate actions, annual netting and broker tax
  statements. The dashboard must not substitute a nominal USD estimate.
- IRA comparison is informational until custody, permitted TQQQ holding,
  wrapper fees, restrictions and withdrawal tax treatment are confirmed.

Security principle: block a number rather than display an invented net value.
