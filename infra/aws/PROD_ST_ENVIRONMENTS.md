# StockLens AWS environment split — PROD + ST (2026-10-28)

## What exists now (do not rename or touch)
- `stocklens-paper`: **retired, disabled legacy**; historical DynamoDB and CloudFormation drift must not be overwritten.
- `stocklens-independent-staging`: **existing candidate**; Signal-only schedule is ON. Its Paper is NOT bootstrapped and its live source/vendor parity remains unproven. This is not an accepted production Paper book.
- GitHub Shadow publishes separate model artifacts. A successful GitHub workflow is not proof of AWS Paper execution.

## Destination (same account, separate stacks)
| | PROD candidate | ST research base |
| --- | --- | --- |
| New CloudFormation stack | `stocklens-prod` | `stocklens-st` |
| Source runtime | SHA-identical ZIP from deployed candidate | same pinned ZIP |
| S3 Paper/Signal data | private, **new**, versioned, not copied | private, **different new bucket**, not copied |
| Lambda / IAM / logs | unique stack-scoped resources | unique stack-scoped resources |
| SNS/KMS and alarms | unique; no email until configured | unique; no email until configured |
| Signal / Paper / combined trading schedules | **DISABLED** | **DISABLED** |
| Hourly watchdog | existing read-only stack template | same |
| Broker access | **NONE** | **NONE** |
| Role | prospective production baseline, needs acceptance | safe isolated integration/strategy experiments |

Both stacks are **infrastructure candidates only** upon creation. The source stack's
existing Signal schedule is unchanged. Do not mislabel the new empty PROD stack
as operational production until separate independently receipted forward Paper,
second-vendor parity, schedule provenance, accounting, alert-delivery and
dashboard-live-source acceptance have succeeded. Do not fabricate or copy old
Paper receipts into either new environment.

The cloned template is the **actually deployed** CloudFormation template of the
source stack, not an unmerged GitHub draft. The immutable artifact ZIP is read
from the source stack Parameters; the script checks that its sha256 exactly
matches the source Lambda CodeSha256. If runtime and artifact disagree, the
provision is refused rather than copying unknown code.

## Operator sequence — from AWS CloudShell in eu-central-1
Use reviewed/pinned GitHub source, not a mutable unverified curl URL.

```bash
bash infra/aws/provision_isolated_prod_st.sh inspect    # READ ONLY
bash infra/aws/provision_isolated_prod_st.sh prepare    # creates only CREATE change sets
# Review the complete ResourceChange list and ongoing AWS cost implications.
bash infra/aws/provision_isolated_prod_st.sh apply      # interactive explicit approval
bash infra/aws/provision_isolated_prod_st.sh inspect    # verify isolated buckets, code SHA, rules
```

The script must be downloaded as an exact pinned commit and verified by Git
blob hash before running. It refuses the wrong AWS account, unexpected source
state, existing destination stacks, unpinned artifact, cross-stack references,
and all update/delete change sets. The two change sets are created **only**
in `prepare`, and are executed **only** in `apply`. An error after creating
one stack is NOT authority to delete or rebuild it; retain evidence and investigate.

The AWS cost budget (20 USD) is **alert-only, not a spend cap**. Two copies
add KMS, CloudWatch, Lambda, SNS and storage costs; validate AWS pricing
before approving. Separate **AWS accounts** with SCP/budget boundaries are
recommended for stronger long-term PROD/ST isolation. Stacks in one account
are resource/IAM isolated but not a security boundary against account admins.

## Research release and promotion contract

1. **PROD:** keep frozen StockLens 8.0 as a baseline. No new model or alternate
   assets are enabled by this infrastructure procedure. No broker credentials
   or secrets. No experimental PR may write to PROD resources.
2. **ST:** deploy challengers explicitly to only `stocklens-st` under a
   separate, reviewed research pipeline/role. Each trial gets an immutable
   experiment ID, full real ETF price provenance, and its own S3
   `research/experiments/<id>/` outputs (ST-only IAM must be granted in a
   reviewed separate change set before research writes).
3. Compare to frozen 8.0 and QQQ/SPY at matched dates, volatility/drawdown
   levels and modeled trading costs; lag-1, next-open, untouched holdouts and
   walk-forward are mandatory. ETF products must have real observed quotes;
   no synthetic 3x history.
4. Promotion is **human-reviewed and manual**, with independent second vendor,
   verified source receipts, no missing sessions, drawdown tests, CI and
   reproducible asset/commit hashes. Never permit automatic PROD promotion.
5. Separate PROD initialization and signed Paper Genesis require a
   **PROD-specific runbook, CloudFormation acceptance and explicit owner consent**.
   Existing `bootstrap_staging_paper_once.sh` is hardcoded to the old staging
   candidate and **MUST NOT be used on PROD or the new ST clone**. Neither
   new stack is automatically scheduled or writes any Paper receipt.

## Next acceptance check
Output must contain:
`ISOLATION_PASS:stocklens-prod`,
`ISOLATION_PASS:stocklens-st`, and
`READ_ONLY_NO_AWS_MUTATIONS`, while all three trading schedules remain DISABLED.
Only then create a separate ST research compute and data permission change set;
do not start by enabling the PROD trading scheduler.
