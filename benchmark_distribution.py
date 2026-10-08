from __future__ import annotations
import statistics

def summarize(relative_windows):
    rows=[x for x in relative_windows if x.get('status')=='PASS' and x.get('excess_cagr') is not None]
    vals=[x['excess_cagr'] for x in rows]; dds=[x.get('drawdown_delta') for x in rows if x.get('drawdown_delta') is not None]
    thirds=[x for x in rows if str(x.get('window_id','')).startswith('THIRD_')]
    tvals=[x['excess_cagr'] for x in thirds]
    return {
      'status':'PASS' if rows else 'BLOCKED',
      'window_count':len(rows),
      'positive_excess_windows':sum(v>0 for v in vals),
      'positive_excess_share':sum(v>0 for v in vals)/len(vals) if vals else None,
      'excess_cagr_min':min(vals) if vals else None,
      'excess_cagr_median':statistics.median(vals) if vals else None,
      'excess_cagr_max':max(vals) if vals else None,
      'excess_cagr_population_stdev':statistics.pstdev(vals) if len(vals)>1 else 0.0 if vals else None,
      'drawdown_delta_median':statistics.median(dds) if dds else None,
      'nonoverlap_thirds':{'window_count':len(thirds),'positive_excess_windows':sum(v>0 for v in tvals),'positive_excess_share':sum(v>0 for v in tvals)/len(tvals) if tvals else None,'excess_cagr_median':statistics.median(tvals) if tvals else None},
      'semantics':'Descriptive benchmark-relative distribution. Rolling windows overlap and are not independent observations. No winner, score, promotion or retuning.'
    }
