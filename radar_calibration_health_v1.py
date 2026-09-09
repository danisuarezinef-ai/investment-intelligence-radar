"""Forward-only calibration health gate.

Historical/simulated observations are not eligible for production calibration claims.
Missing mature evidence remains INSUFFICIENT_EVIDENCE.
"""
REAL_TRADING=False


def calibration_health(*, mature_forward_n=0, calibration_error=None, benchmark_coverage=0.0, cost_coverage=0.0, backfilled_n=0, min_n=50, max_calibration_error=0.12):
    blockers=[]
    n=int(mature_forward_n or 0)
    if int(backfilled_n or 0)>0: blockers.append('BACKFILL_PRESENT')
    if n<int(min_n): blockers.append('INSUFFICIENT_MATURE_FORWARD')
    if calibration_error is None: blockers.append('CALIBRATION_NOT_MEASURED')
    elif float(calibration_error)>float(max_calibration_error): blockers.append('CALIBRATION_DEGRADED')
    if float(benchmark_coverage or 0.0)<0.95: blockers.append('BENCHMARK_COVERAGE_LOW')
    if float(cost_coverage or 0.0)<0.95: blockers.append('COST_COVERAGE_LOW')
    return {
        'status':'PASS' if not blockers else 'BLOCKED',
        'blockers':blockers,
        'mature_forward_n':n,
        'calibration_error':calibration_error,
        'real_trading':False,
    }
