"""Decision Intelligence v2.
Turns forecasts into auditable investment decisions. Real trading is deliberately unsupported.
"""
from dataclasses import dataclass, asdict
import math

REAL_TRADING=False
ACTIONS=('BUY','HOLD','REDUCE','AVOID','WAIT')


def clamp(x,a=0.0,b=1.0): return max(a,min(b,float(x)))

def geometric_mean(xs):
    xs=[max(1e-9,float(x)) for x in xs]
    return math.exp(sum(math.log(x) for x in xs)/len(xs)) if xs else 0.0

@dataclass
class Uncertainty:
    model_confidence: float
    disagreement: float
    data_quality: float
    epistemic: float
    regime: float
    def confidence(self):
        # confidence cannot be rescued by a single excellent component
        positive=geometric_mean([clamp(self.model_confidence),clamp(self.data_quality),1-clamp(self.epistemic),1-clamp(self.regime)])
        return clamp(positive*(1-0.70*clamp(self.disagreement)))

@dataclass
class Decision:
    symbol:str; horizon:str; action:str; conviction:float; opportunity_score:float
    confidence:float; expected_return:float; downside:float; valuation_risk:float
    reason:str; real_trading:bool=False
    def payload(self): return asdict(self)


def opportunity_score(expected_return, downside, confidence, valuation_risk, liquidity=1.0, cost=0.0, alternative_return=0.0):
    """Utility-like score relative to the best alternative, not an absolute forecast score."""
    excess=float(expected_return)-float(alternative_return)-float(cost)
    risk_penalty=0.55*max(0.0,float(downside))+0.35*max(0.0,float(valuation_risk))
    return (excess-risk_penalty)*clamp(confidence)*clamp(liquidity)


def decide(symbol,horizon,expected_return,downside,valuation_risk,uncertainty,alternative_return=0.0,cost=0.0,liquidity=1.0):
    conf=uncertainty.confidence() if isinstance(uncertainty,Uncertainty) else clamp(uncertainty)
    score=opportunity_score(expected_return,downside,conf,valuation_risk,liquidity,cost,alternative_return)
    if conf < .42: action,reason='WAIT','insufficient confidence / model disagreement'
    elif score >= 2.5 and expected_return > alternative_return: action,reason='BUY','positive risk-adjusted opportunity versus alternatives'
    elif score >= .25: action,reason='HOLD','positive but insufficient margin for new capital'
    elif expected_return < 0 or score < -1.0: action,reason='AVOID','negative opportunity after risk and alternatives'
    else: action,reason='REDUCE','weak opportunity or deteriorating margin of safety'
    return Decision(symbol,horizon,action,clamp(conf*min(1,abs(score)/5+.25)),score,conf,float(expected_return),float(downside),float(valuation_risk),reason,False)


def master_investor_score(metrics):
    """0..100 score. Rewards robust risk-adjusted, calibrated performance rather than raw return."""
    m=lambda k,d=.5: clamp(metrics.get(k,d))
    reward=(.18*m('risk_adjusted_return')+.12*m('cagr')+.12*m('sortino')+.10*m('calibration')+.08*m('hit_rate')+.10*m('stability')+.08*m('tail_resilience')+.07*m('cost_efficiency')+.08*m('regime_robustness')+.07*m('abstention_quality'))
    penalty=.10*m('drawdown_severity')+.05*m('turnover_excess')+.05*m('concentration_risk')
    return round(100*clamp(reward-penalty),3)
