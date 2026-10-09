# Secure StockLens DynamoDB history inside the AWS Amplify dashboard

The dashboard already has **per-trade modeled cost breakdowns**, **expected-exchange-session gap tracking** from Yahoo, and **A/B investment scenarios** computed from the exact observed TQQQ and QQQ execution-proxy history. These work immediately from the existing published artifacts.

## Optional private DynamoDB read, requiring a separate AWS deployment

The previously deployed stocklens-paper stack is untouched and must remain broker-disabled. Never expose its DynamoDB table via a public API or place AWS access keys in a frontend file.

To enable direct authenticated reads:
1. Open AWS CloudFormation in eu-central-1, **Create stack** (NOT Update stocklens-paper).
2. Upload infra/aws/portal-readonly-api.yaml. Use stack name stocklens-portal-read.
3. Set JournalTableName to the physical name of the existing stocklens-paper Signals table, e.g. find it in DynamoDB -> Tables. The new role has only **dynamodb:GetItem** permission to that one exact table.
4. Keep AmplifyOrigin as https://main.d20nvlvzjafg5m.amplifyapp.com (no trailing slash). Pick a globally unique lowercase CognitoDomainPrefix.
5. Review IAM role creation and confirm CREATE_COMPLETE. This creates: Cognito user pool with public signup **disabled**, one OAuth PKCE browser client with no client secret, JWT-protected API Gateway route, a Lambda with GetItem-only and read-only CORS.
6. In Cognito user pool -> Users, use **Create user** to invite a permitted email. All other visitors remain unauthorized. Use HTTPS Cognito hosted sign-in.
7. Open the new CloudFormation stack's Outputs. Copy ApiBaseUrl, CognitoDomain, CognitoClientId.
8. Create a **public, non-secret** file docs/cloud-config.json in GitHub main using docs/cloud-config.example.json as a guide. Set enabled=true and paste the three Output values, keeping redirect_uri exactly https://main.d20nvlvzjafg5m.amplifyapp.com/portal.html. Let Amplify rebuild.
9. Open the Paper Trading section on the AWS site, choose **התחברות מאובטחת ל־AWS**, sign in via Cognito and press **טעינת רשומות DynamoDB**. All JWTs stay in browser memory, never localStorage or the repo.
10. Verify rows for 2026-10-08 and later. A record is PASS only if both the signal and modeled paper SHA-256 hashes, dates, counts and broker-disabled flags match; missing/invalid records remain visibly marked, never silently filled. Revisit after each completed session.

Do **not** add AWS key ID, secret access key, refresh token, personal email or ID token into cloud-config.json. The API base URL, Cognito public client ID and hosted domain are designed to be public. The API itself rejects requests without a valid Cognito JWT. This is different from the original public static research feeds.

## What happens before AWS creation?

The interface still runs normally. It labels the DynamoDB button disabled and explains that it is showing a GitHub-published **snapshot**. It never pretends that snapshot was fetched live from DynamoDB. No real order can be submitted.

## Trade-detail and scenario semantics

Click a trade row in Paper to see reference price, modeled fill price, per-trade commission and slippage, originating prior-session signal and end-of-day NAV when present. Execution-proxy costs are not brokerage statements; unrealized P/L cannot be assigned to the one trade without holdings-level accounting.

The A/B simulator uses the SAME dates, frozen signals and the SAME observed Yahoo QQQ and TQQQ daily adjusted opens/closes. A and B may choose different initial capital, deposits and slippage assumptions. Comparison explicitly separates paid capital from modeled profit. Neither replaces the approved StockLens 8.0 trading algorithm or authorizes live trading.

## Security / operational caveats

- Cognito admin-only signup is critical. Do not make self-registration public.
- Even though CORS allows the specific Amplify site only, **CORS is not an authentication boundary**. API Gateway JWT authorizer is mandatory and covers the only route.
- Access tokens are never saved in localStorage, cookies, screenshots or workflow artifacts by our portal code. They are kept only in memory. A new tab or refresh requires a new sign-in.
- No DynamoDB Scan/Put/Update/Delete/IAM expansion on the existing journal stack.
- The legacy public repository still has public strategy/research snapshots. Authenticating the private AWS journal does not make those static files private.
- For stronger operational use, configure CloudWatch API metrics, throttling, Cognito MFA and account security policy; rotate credentials and revoke accounts as needed. Monitor DynamoDB provisioned read capacity.
