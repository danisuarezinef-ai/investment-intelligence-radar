"""Fail-closed diversification guard for PAPER allocations."""
REAL_TRADING=False


def diversification_guard(*, positions=None, max_single_weight=0.20, max_sector_weight=0.40, pairwise_correlations=None, max_pair_corr=0.90):
    positions=positions or []
    blockers=[]
    sector_weights={}
    for p in positions:
        try:w=float(p.get('weight'))
        except Exception:
            blockers.append('INVALID_WEIGHT'); continue
        if w<0: blockers.append('NEGATIVE_WEIGHT')
        if w>float(max_single_weight): blockers.append('SINGLE_NAME_CONCENTRATION')
        sector=str(p.get('sector') or 'UNKNOWN')
        sector_weights[sector]=sector_weights.get(sector,0.0)+max(0.0,w)
    for sector,w in sector_weights.items():
        if sector!='UNKNOWN' and w>float(max_sector_weight): blockers.append('SECTOR_CONCENTRATION')
    for corr in pairwise_correlations or []:
        try:
            if abs(float(corr))>float(max_pair_corr): blockers.append('CORRELATION_CLUSTER')
        except Exception: blockers.append('INVALID_CORRELATION')
    blockers=sorted(set(blockers))
    return {'status':'PASS' if not blockers else 'BLOCKED','blockers':blockers,'sector_weights':sector_weights,'real_trading':False}
