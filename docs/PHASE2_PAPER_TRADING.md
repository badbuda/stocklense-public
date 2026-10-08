# StockLens Phase 2: paper execution with observed ETFs

This branch completes an independent paper-ledger accounting and causal check within the existing daily StockLens Shadow pipeline. It does not introduce broker orders, rewrite frozen 8.0, fabricate paper sessions or alter historical returns.

Existing paper execution: prior completed QQQ adjusted close signal; next NYSE session observed QQQ/TQQQ one-minute OPEN prices, sells at 09:31 ET and buys at 09:32 ET; simulated whole shares, available cash, modeled 2 bps fees and 10 bps slippage per side. State, trade ledger and continuity report are retained as evidence only.

New audit: verifies signal was saved before market open, freeze-aligned target weight, exact QQQ/TQQQ observed-minute source (not synthetic leveraged returns), per-order fee and slippage formulas, account equity and return accounting, cumulative charges, turnover and cash conservation. Fails CI on invalid forward paper evidence. Empty ledgers explicitly remain WAITING.

AWS today stores frozen shadow signal in DynamoDB only. It has a read-only GitHub OIDC audit role. Deployment of an AWS paper ledger, an AWS price sampler or broker connectivity would require a reviewed CloudFormation update: these are NOT already running. Avoid presenting an observed Yahoo minute OPEN or modeled fill as broker bid/ask, execution or realized P&L.

Broker integration recommended in read-only mode first. Excellence GlobalEXtrade public information advertises API capability: https://www.xnes.co.il/trading/globalextrade/ . Must verify eligibility and official docs for this particular user's account. IBKR Web/TWS API is an alternative: https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-trading/ . Both require their own provider authentication and data entitlements. Never disclose credentials in chat.

Next gates: first verified forward paper session, independent broker quote and account data, paired QQQ benchmark, idempotent realtime journal, guardrails, and human authorization before any capital or automated broker orders.
