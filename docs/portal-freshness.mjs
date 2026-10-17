/* Publication freshness, not market/portfolio readiness. Pure, deterministic and fail-closed. */
const DAY_MS = 86400000;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/* Calendar-day threshold (4) tolerates ordinary weekends and a long weekend.
   It is not a precise XNYS calendar. Flagging extra stale days is safer than
   depicting historic snapshots as live AWS trading/accounting evidence. */
export function publicationFreshness({signalDate, paperDate, historyDate, riskDate}, now = new Date()) {
  const feeds = {signal: signalDate, paper: paperDate, history: historyDate, risk: riskDate};
  const nowDay = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const invalid = [], stale = [];
  const normalized = {};
  if (!Number.isFinite(now.getTime())) throw Error('INVALID_FRESHNESS_CLOCK');
  for (const [name, value] of Object.entries(feeds)) {
    const parsed = typeof value === 'string' && DATE_RE.test(value)
      ? Date.parse(value + 'T00:00:00Z') : NaN;
    if (!Number.isFinite(parsed) || new Date(parsed).toISOString().slice(0, 10) !== value || parsed > nowDay) {
      invalid.push(name); continue;
    }
    normalized[name] = value;
    if (Math.floor((nowDay - parsed) / DAY_MS) > 4) stale.push(name);
  }
  const distinct = new Set(Object.values(normalized));
  const inconsistent = distinct.size > 1;
  return {
    healthy: invalid.length === 0 && stale.length === 0 && !inconsistent,
    invalid, stale, inconsistent, dates: normalized,
    oldestDate: Object.values(normalized).sort()[0] || null
  };
}

export function publicationMessage(result) {
  if (result.invalid.length) return 'נתוני האתר חסרים, עתידיים או לא תקינים; אין להסתמך עליהם כסיגנל נוכחי.';
  if (result.inconsistent) return 'פער תאריכים בין סיגנל, תיק Paper, היסטוריה וסיכון; הנתונים אינם תמונת מצב עקבית.';
  if (result.stale.length) return 'נתוני האתר מיושנים (פרסום אחרון ' + result.oldestDate + '). אין סיגנל או שווי Paper עדכני באתר.';
  return 'צילום מצב מקובצי GitHub; אין חיבור אוטומטי למנוע ה־AWS החדש ואין כאן ציטוטים בזמן אמת.';
}
