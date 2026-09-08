"""Transparent scenario stress tests for paper portfolios."""
SCENARIOS={
 'rates_up':{'rates':1,'growth':-.35,'duration':-.60},
 'inflation_shock':{'inflation':1,'rates':.55,'commodities':.45},
 'tech_drawdown':{'technology':-1,'growth':-.65,'volatility':.70},
 'energy_shock':{'energy':1,'inflation':.60,'consumer':-.35},
 'geopolitical_risk':{'geopolitics':1,'volatility':.75,'global_trade':-.55},
 'correlation_spike':{'correlation':1,'volatility':.65},
}

def stress_portfolio(weights,exposures,scenario):
 shocks=SCENARIOS.get(scenario,scenario if isinstance(scenario,dict) else {})
 asset={}
 for sym,w in weights.items():
  impact=sum(float(exposures.get(sym,{}).get(f,0))*float(shock) for f,shock in shocks.items())
  asset[sym]=impact
 return {'scenario':scenario if isinstance(scenario,str) else 'custom','portfolio_impact':sum(float(weights[s])*asset[s] for s in weights),'asset_impacts':asset,'assumption_based':True,'real_trading':False}
