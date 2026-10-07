from __future__ import annotations

from datetime import datetime, time
import hashlib
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

HISTORY_START = "2008-01-01"
NY_TZ = ZoneInfo("America/New_York")
DAILY_BAR_SAFE_AFTER = time(18, 0)


def _feature_window_sha256(out: pd.DataFrame, sessions: int = 253) -> str:
    if len(out) < sessions:
        raise ValueError(f"Need at least {sessions} rows for feature-window fingerprint")
    tail = out.iloc[-sessions:]
    payload = "\n".join(
        f"{pd.Timestamp(row.Date).date().isoformat()},{float(row.Close):.12g}"
        for row in tail.itertuples(index=False)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _drop_incomplete_current_session(
    out: pd.DataFrame,
    now_ny: datetime | None = None,
) -> tuple[pd.DataFrame, dict]:
    if out.empty:
        return out, {
            "raw_last_date": None,
            "last_completed_date": None,
            "dropped_incomplete_current_session": False,
        }
    now_ny = now_ny or datetime.now(NY_TZ)
    if now_ny.tzinfo is None:
        now_ny = now_ny.replace(tzinfo=NY_TZ)
    else:
        now_ny = now_ny.astimezone(NY_TZ)

    raw_last = pd.Timestamp(out.iloc[-1]["Date"]).date()
    dropped = False
    if raw_last == now_ny.date() and now_ny.time() < DAILY_BAR_SAFE_AFTER:
        out = out.iloc[:-1].copy()
        dropped = True

    completed_last = pd.Timestamp(out.iloc[-1]["Date"]).date().isoformat() if not out.empty else None
    return out, {
        "raw_last_date": raw_last.isoformat(),
        "last_completed_date": completed_last,
        "dropped_incomplete_current_session": dropped,
        "ny_time_at_validation": now_ny.isoformat(),
        "safe_after_ny_time": DAILY_BAR_SAFE_AFTER.strftime("%H:%M"),
    }


def load_qqq_history(
    csv_path: str | None = None,
    now_ny: datetime | None = None,
) -> tuple[pd.DataFrame, dict]:
    if csv_path:
        p = Path(csv_path)
        df = pd.read_csv(p)
        lower = {c.lower(): c for c in df.columns}
        date_col = lower.get("date")
        close_col = lower.get("adj close") or lower.get("close")
        if not date_col or not close_col:
            raise ValueError("CSV must contain Date and Close or Adj Close columns")
        out = pd.DataFrame({
            "Date": pd.to_datetime(df[date_col]),
            "Close": pd.to_numeric(df[close_col], errors="coerce"),
        })
        source = f"CSV:{p}"
    else:
        import yfinance as yf
        df = yf.download(
            "QQQ",
            start=HISTORY_START,
            interval="1d",
            auto_adjust=True,
            progress=False,
            actions=False,
            threads=False,
        )
        if df is None or df.empty:
            raise RuntimeError("No QQQ data returned by yfinance")
        close = df["Close"]["QQQ"] if isinstance(df.columns, pd.MultiIndex) else df["Close"]
        out = pd.DataFrame({
            "Date": pd.to_datetime(close.index),
            "Close": pd.to_numeric(close.values, errors="coerce"),
        })
        source = "YFINANCE_QQQ_AUTO_ADJUSTED"

    out = out.dropna().drop_duplicates("Date").sort_values("Date")
    out = out[out["Close"] > 0].reset_index(drop=True)
    raw_rows = len(out)
    out, completion_audit = _drop_incomplete_current_session(out, now_ny=now_ny)

    if len(out) < 300:
        raise RuntimeError(f"Only {len(out)} valid completed QQQ daily rows")
    if out.iloc[0]["Date"].date().isoformat() > "2008-01-10":
        raise RuntimeError("History starts too late for exact 2009 StockLens state reconstruction")

    audit = {
        "source": source,
        "raw_rows": raw_rows,
        "completed_rows": len(out),
        "feature_window_sessions": 253,
        "feature_window_sha256": _feature_window_sha256(out, 253),
        **completion_audit,
    }
    return out.reset_index(drop=True), audit


def load_tqqq_history(now_ny: datetime | None = None) -> tuple[pd.DataFrame, dict]:
    """Observed TQQQ adjusted daily closes from fund inception onward."""
    import yfinance as yf
    df = yf.download(
        "TQQQ",
        start="2010-02-09",
        interval="1d",
        auto_adjust=True,
        progress=False,
        actions=False,
        threads=False,
    )
    if df is None or df.empty:
        raise RuntimeError("No TQQQ data returned by yfinance")
    close = df["Close"]["TQQQ"] if isinstance(df.columns, pd.MultiIndex) else df["Close"]
    out = pd.DataFrame({"Date": pd.to_datetime(close.index), "Close": pd.to_numeric(close.values, errors="coerce")})
    out = out.dropna().drop_duplicates("Date").sort_values("Date")
    out = out[out["Close"] > 0].reset_index(drop=True)
    raw_rows=len(out)
    out, completion_audit=_drop_incomplete_current_session(out,now_ny=now_ny)
    if out.empty or out.iloc[0]["Date"].date().isoformat() > "2010-02-12":
        raise RuntimeError("TQQQ history does not reach fund inception window")
    return out,{"source":"YFINANCE_TQQQ_AUTO_ADJUSTED","raw_rows":raw_rows,"completed_rows":len(out),"inception_date":"2010-02-09",**completion_audit}
