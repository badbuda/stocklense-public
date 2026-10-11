# SL9-026 — Claude H2: two-consecutive-completed-session VIX > VIX3M

Predeclared October 11, 2026 BEFORE this variant's experiment. Source is
exact archived official Cboe VIX+VIX3M index snapshot ZIP from Oct 11 SL9-021,
snapshot bytes SHA256 0ff8ef25ee51388e39d53378fad2ba233b8e9e7c5fa55cf765e550a399c77749.
Source CI run 38118290769, artifact id 11694158242. Do not re-fetch.

One fixed signal: if prior completed trading session t-1 VIX/VIX3M > 1
AND previous completed session t-2 VIX/VIX3M > 1, cap frozen StockLens
exposure 3x at 2x; no change to 0/1.25/2x. First 2 days warmup unchanged.
Compare frozen exact daily NAV in 0/1 extra signal/feature delay by
10/20bps modeled trade-side slippage and 2bps fees. No synthetic TQQQ,
physical observed adjusted QQQ and TQQQ daily opens, no actual NBBO or
broker fills. No clean OOS; older H2 single-day was already tried and
rejected. New 2-day H2 is sequential exploratory selection, not
an independent hypothesis test.

Prespecified continuation (RESEARCH ONLY, no automatic promotion):
ALL four matched lag/cost cells show ≥3pp improvement in peak-to-trough
MaxDD and no >0.5pp annual CAGR cost; plus a one-sided exploratory
1,000 placebo randomization tail probability ≤0.01 on gross CAGR
with seed 20261011. Placebos must reduce exactly K frozen-3x
sessions, K = real challenger intervention days, cap to same 2x.
NOTE: randomized DAYS are not matched in number or length of episodes
or turnover; costless placebo avoids obvious unequal fees but is NOT a
statistically valid corrected p-value. Report randomization distribution,
interventions, trades and this material limitation. No threshold tuning
or retest if negative; hold original baseline frozen.
