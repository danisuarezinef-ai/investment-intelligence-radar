import json
from datetime import datetime, timezone, timedelta

from radar_core import con, init_db, now
from radar_learning import init_learning_db

ENTITY_RULES = {
    'AI_COMPUTE': ['artificial intelligence',' ai ','gpu','semiconductor','chip','accelerator'],
    'GRID_POWER': ['grid','electricity','power demand','data center power','transmission'],
    'BATTERIES': ['battery','lithium','energy storage'],
    'QUANTUM': ['quantum'],
    'BIOTECH': ['drug','clinical trial','fda','biotech','pharma'],
    'DEFENSE': ['defense','missile','military','drone','weapons'],
    'TRADE_CONTROLS': ['tariff','sanction','export control','trade restriction'],
}

SYMBOL_TERMS = {
    'MSFT':['microsoft'], 'NVDA':['nvidia'], 'GOOGL':['google','alphabet'], 'AMZN':['amazon','aws'],
    'META':['meta platforms','facebook'], 'AVGO':['broadcom'], 'ASML':['asml'], 'SAP':['sap'],
    'TSM':['tsmc','taiwan semiconductor'], 'TM':['toyota'], 'SHEL':['shell'], 'RIO':['rio tinto'],
    'LLY':['eli lilly','lilly'], 'V':['visa'], 'BRK-B':['berkshire'], 'NVS':['novartis']
}

STRUCTURAL_EDGES = [
    ('AI_COMPUTE','raises_demand_for','NVDA',1,0.88),
    ('AI_COMPUTE','raises_demand_for','AVGO',1,0.78),
    ('AI_COMPUTE','raises_demand_for','TSM',1,0.82),
    ('AI_COMPUTE','raises_demand_for','ASML',2,0.72),
    ('AI_COMPUTE','raises_power_demand','GRID_POWER',2,0.83),
    ('GRID_POWER','supports','SHEL',3,0.42),
    ('BATTERIES','raises_material_demand','RIO',2,0.58),
    ('TRADE_CONTROLS','supply_chain_risk','TSM',1,0.74),
    ('TRADE_CONTROLS','supply_chain_risk','ASML',1,0.74),
    ('DEFENSE','sector_tailwind','AVGO',3,0.35),
    ('BIOTECH','sector_signal','LLY',2,0.52),
    ('BIOTECH','sector_signal','NVS',2,0.52),
]


def _topics(title):
    t=' '+str(title or '').lower()+' '
    out=[]
    for topic,terms in ENTITY_RULES.items():
        if any(term in t for term in terms): out.append(topic)
    return out


def _symbols(title):
    t=str(title or '').lower(); out=[]
    for sym,terms in SYMBOL_TERMS.items():
        if any(term in t for term in terms): out.append(sym)
    return out


def _insert_edge(c,source,relation,target,depth,confidence,event_id,horizon='medium',metadata=None):
    row=c.execute('''select 1 from causal_edges where source_node=? and relation=? and target_node=? and evidence_event_id=? limit 1''',(source,relation,target,event_id)).fetchone()
    if row:return False
    c.execute('''insert into causal_edges(created_at,source_node,relation,target_node,depth,confidence,evidence_event_id,horizon,metadata)
                 values(?,?,?,?,?,?,?,?,?)''',(now(),source,relation,target,int(depth),float(confidence),event_id,horizon,json.dumps(metadata or {})))
    return True


def build_causal_graph(hours=168):
    init_db(); init_learning_db(); cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat(); c=con()
    events=c.execute('select id,ts,source,title,category from information_events where ts>=? order by id',(cutoff,)).fetchall(); created=0
    for eid,ts,src,title,category in events:
        topics=_topics(title); syms=_symbols(title)
        for topic in topics:
            for sym in syms:
                created+=1 if _insert_edge(c,topic,'direct_signal',sym,1,0.72,eid,'short',{'source':src,'title':title}) else 0
            for a,rel,b,depth,conf in STRUCTURAL_EDGES:
                if a==topic:
                    created+=1 if _insert_edge(c,a,rel,b,depth,conf,eid,'medium',{'source':src,'title':title}) else 0
        for sym in syms:
            for topic in topics:
                created+=1 if _insert_edge(c,sym,'exposed_to',topic,1,0.65,eid,'short',{'source':src}) else 0
    c.commit(); c.close(); return created


def causal_paths(node,max_depth=3,limit=50):
    init_learning_db(); c=con(); frontier=[(node,[],1.0)]; seen=set(); paths=[]
    while frontier and len(paths)<limit:
        current,path,score=frontier.pop(0)
        if len(path)>=max_depth:continue
        rows=c.execute('''select relation,target_node,confidence,evidence_event_id,horizon from causal_edges where source_node=? order by confidence desc limit 30''',(current,)).fetchall()
        for rel,target,conf,eid,horizon in rows:
            key=(current,rel,target,eid)
            if key in seen:continue
            seen.add(key); step={'source':current,'relation':rel,'target':target,'confidence':float(conf),'event_id':eid,'horizon':horizon}
            newpath=path+[step]; newscore=score*float(conf); paths.append({'path':newpath,'path_confidence':newscore})
            frontier.append((target,newpath,newscore))
    c.close(); return sorted(paths,key=lambda x:x['path_confidence'],reverse=True)[:limit]


def symbol_causal_summary(symbol):
    init_learning_db(); c=con(); inbound=c.execute('''select source_node,relation,depth,confidence,evidence_event_id,horizon from causal_edges where target_node=? order by confidence desc limit 20''',(symbol,)).fetchall(); outbound=c.execute('''select relation,target_node,depth,confidence,evidence_event_id,horizon from causal_edges where source_node=? order by confidence desc limit 20''',(symbol,)).fetchall(); c.close()
    return {'symbol':symbol,'inbound':[{'source':r[0],'relation':r[1],'depth':r[2],'confidence':r[3],'event_id':r[4],'horizon':r[5]} for r in inbound], 'outbound':[{'relation':r[0],'target':r[1],'depth':r[2],'confidence':r[3],'event_id':r[4],'horizon':r[5]} for r in outbound], 'paths':causal_paths(symbol,3,20)}


def graph_summary():
    init_learning_db(); c=con(); total=c.execute('select count(*) from causal_edges').fetchone()[0]; top=c.execute('''select source_node,count(*) n from causal_edges group by source_node order by n desc limit 10''').fetchall(); c.close(); return {'edges':total,'top_sources':[{'node':r[0],'edges':r[1]} for r in top]}
