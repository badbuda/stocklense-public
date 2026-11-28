"""SL-51 paired opening-price proxy for the cost of unchanged-target rebalancing."""
import json

from observed_etf_two_question_audit import load, _metrics, _run
from paper_rebalance_math import within_band
from stocklens.core import TARGET_INVESTED_FRACTION, weights_for_leverage
from stocklens.paper import SessionMarket, new_state, rebalance_if_required, _portfolio_value


def replay(rows, band):
    state = new_state()
    prior = None
    nav = []
    drift_sessions = 0
    turnover = 0.0
    for row in rows:
        level = row["l"]
        q, t = weights_for_leverage(level)
        weights = {"QQQ": q * TARGET_INVESTED_FRACTION, "TQQQ": t * TARGET_INVESTED_FRACTION}
        opens = {"QQQ": row["qo"], "TQQQ": row["to"]}
        closes = {"QQQ": row["qc"], "TQQQ": row["tc"]}
        equity = _portfolio_value(state, opens)
        changed = prior != level
        if changed or (band is not None and not within_band(state["shares"], weights, opens, equity, band)):
            # The research band decision is complete. Reuse Paper sell-before-buy sizing for all arms.
            market = SessionMarket(row["date"], opens, opens, closes, {}, {}, source="ADJUSTED_DAILY_OPEN_PROXY")
            signal = {"latest": {"qqq_weight": weights["QQQ"], "tqqq_weight": weights["TQQQ"],
                                 "asof_date": row["signal"]}, "action": "REBALANCE_NEXT_SESSION"}
            trades = rebalance_if_required(state, signal, market, prior is None)
            drift_sessions += int(bool(trades) and not changed)
            turnover += sum(t["gross_notional"] for t in trades) / equity
        nav.append(_portfolio_value(state, closes))
        prior = level
    metrics = _metrics(nav, [r["date"] for r in rows])
    return {**{k: metrics[k] for k in ("ending_equity", "cagr", "max_drawdown")},
            "orders": state["trade_count"], "drift_sessions": drift_sessions,
            "summed_one_way_turnover": turnover,
            "fees": state["cumulative_fees"], "slippage": state["cumulative_slippage_cost"]}


def main():
    rows = load()["daily"]
    for label, subset in [("all", rows), ("2018-2022", [r for r in rows if "2018" <= r["date"] < "2023"]),
                          ("2023+", [r for r in rows if r["date"] >= "2023"])]:
        arms = {str(b): replay(subset, b) for b in [None, .0025, .005, .01, .02]}
        print(json.dumps({"period": label, "start": subset[0]["date"], "end": subset[-1]["date"],
                          "sessions": len(subset), "historical_engine": _run(subset)["stats"]["ending_equity"],
                          "arms": arms}))


if __name__ == "__main__":
    main()
