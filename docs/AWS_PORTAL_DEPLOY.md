# StockLens Portal on AWS Amplify

## What is in this repository
The new home page redirects to the six-screen Hebrew portal. Its published historical performance uses observed Yahoo QQQ/TQQQ adjusted daily prices, not synthetic 3x QQQ returns. The signal and historical paper trading remain distinct. The simulator lets a reader choose starting cash, monthly contribution, dates and assumed trading costs. There are no broker orders or AWS credentials in browser code.

## One-time AWS connection
This repo's current AWS journal role is read-only and cannot deploy a site. The account owner must connect AWS Amplify Hosting once:

1. Open https://eu-central-1.console.aws.amazon.com/amplify/home?region=eu-central-1#/
2. Choose Create new app -> GitHub, authorize ONLY badbuda/stocklense-public and select branch main.
3. Set app name stocklens-portal. Amplify finds the root amplify.yml, publishing baseDirectory: docs. Do not provision a backend, give broker credentials or escalate the existing audit role.
4. Review the initial build. AWS will provide a generated app URL in Hosting -> Overview. We cannot know that URL before the app exists.
5. In Hosting -> Access control, consider password-protecting the branch. The original public GitHub data remain public despite a website password.
6. Turn on automatic deployment for main. Once the initial observed-price feed is generated, further completed-session updates from GitHub automatically refresh the Amplify site.

## Data pipeline
The frozen StockLens Shadow workflow already downloads Yahoo QQQ and TQQQ. It now calls portal_feed.py after observed ETF risk validation and publishes docs/portal-history.json with SHA-matched QQQ/TQQQ price opens and closes. A one-time workflow portal-history-build.yml creates the first feed on merging. When the historical price feed is absent or invalid, the simulator stays disabled; never fabricate TQQQ with QQQ multiplied by 3.

The DynamoDB journal CSV export remains available at https://github.com/badbuda/stocklense-public/actions/workflows/aws-journal-export.yml. This UI does not expose DynamoDB directly to browsers.

## Acceptance criteria
- GitHub Fast Guard, source fingerprint and all dashboard tests pass.
- The new home loads all six screens from both desktop and mobile.
- portal-history.json contains observed_ohlc_available=true and at least 3,000 historical trading sessions with valid adjusted prices.
- Historical chart shows both StockLens and QQQ observed-ETF execution-proxy paths, with methodology clearly labeled.
- The simulator changes results and modeled transaction receipts when dates, starting capital, deposits or fees change.
- Paper holdings and trades use only committed forward sessions and never show simulated broker fills.
- Amplify's own deployment shows successful publish, main-site URL loads, and automatic rebuild works on subsequent validated data commits.

## Limitations
These historical trades use Yahoo adjusted daily OPEN price proxies and assumed fills/fees, not real LEAN/broker intraday execution. Published GitHub data are public. Future returns and live brokerage readiness are not proven. AWS app creation is a separate account action requiring the owner; a merged buildspec alone is not deployment.
