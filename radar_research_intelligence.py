"""Research Intelligence v0: prioritizes uncertainty and adversarially reviews theses."""
from dataclasses import dataclass,asdict

def clamp(x,a=0,b=1):return max(a,min(b,float(x)))

def value_of_information(decision_impact,uncertainty,resolvability,cost=.1):
 return clamp(decision_impact)*clamp(uncertainty)*clamp(resolvability)-max(0,float(cost))

def research_queue(questions,budget=5):
 rows=[]
 for q in questions:
  x=dict(q);x['voi']=value_of_information(x.get('decision_impact',0),x.get('uncertainty',0),x.get('resolvability',0),x.get('cost',.1));rows.append(x)
 return sorted(rows,key=lambda x:x['voi'],reverse=True)[:budget]

def allocate_evidence_budget(questions,total=100):
 q=research_queue(questions,len(questions));positive=[x for x in q if x['voi']>0];den=sum(x['voi'] for x in positive) or 1
 return [{'question':x.get('question'),'budget':round(total*x['voi']/den,2),'voi':x['voi']} for x in positive]

ROLES=('bull','bear','valuation','macro','causal','risk')
def investment_committee(arguments):
 """Preserves disagreement. arguments={role:{score:-1..1, evidence:[...]}}"""
 rows=[]
 for role in ROLES:
  a=arguments.get(role,{});rows.append({'role':role,'score':max(-1,min(1,float(a.get('score',0)))),'evidence':a.get('evidence',[])})
 mean=sum(x['score'] for x in rows)/len(rows);spread=max(x['score'] for x in rows)-min(x['score'] for x in rows)
 return {'roles':rows,'consensus':mean,'disagreement':spread/2,'requires_review':spread>1.2}

def red_team(thesis,attack_scenarios):
 ranked=sorted(attack_scenarios,key=lambda x:float(x.get('severity',0))*float(x.get('plausibility',0)),reverse=True)
 return {'thesis':thesis,'attacks':ranked,'max_risk':(float(ranked[0].get('severity',0))*float(ranked[0].get('plausibility',0)) if ranked else 0)}

def premortem(symbol,loss=.40):
 return {'symbol':symbol,'assumed_loss':-abs(float(loss)),'questions':['Which thesis assumption failed?','Which risk was visible but underweighted?','Was valuation/margin of safety insufficient?','Did correlations/regime change?','Was evidence stale, crowded or already priced in?','What observation today would warn us earliest?']}

def autonomous_research_proposal(uncertainty):
 """Proposal only. It cannot promote a model or trade."""
 return {'question':uncertainty['question'],'hypothesis':uncertainty.get('hypothesis'),'required_evidence':uncertainty.get('required_evidence',[]),'experiment':uncertainty.get('experiment'),'promotion_allowed':False,'real_trading':False}
