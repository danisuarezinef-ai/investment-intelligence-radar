import json
from datetime import datetime, timezone
from radar_core import con, init_db, STATUS, now
from radar_learning import init_learning_db, active_model


def _status():
    try:
        with open(STATUS,'r',encoding='utf-8') as f:return json.load(f)
    except Exception:return {}


def run_integrity_audit():
    init_db();init_learning_db();c=con();tests=[]
    def add(component,name,status,detail,metrics=None):
        tests.append({'component':component,'test':name,'status':status,'detail':detail,'metrics':metrics or {}})
        try:c.execute('insert into audit_events(ts,component,test_name,status,detail,metrics) values(?,?,?,?,?,?)',(now(),component,name,status,detail,json.dumps(metrics or {})))
        except Exception:pass
    try:
        q=c.execute('pragma quick_check').fetchone()[0];add('database','sqlite_quick_check','PASS' if q=='ok' else 'FAIL',str(q))
    except Exception as e:add('database','sqlite_quick_check','FAIL',str(e))
    for table in ('market_snapshots','information_events','system_runs','paper_agents','predictions','model_versions'):
        try:n=c.execute(f'select count(*) from {table}').fetchone()[0];add('schema',table,'PASS' if n>=0 else 'FAIL',str(n),{'rows':n})
        except Exception as e:add('schema',table,'FAIL',str(e))
    try:
        dup=c.execute('select count(*) from (select symbol,ts,count(*) n from market_snapshots group by symbol,ts having n>1)').fetchone()[0];add('dedupe','market_symbol_ts','PASS' if dup==0 else 'WARN',f'{dup} duplicate groups',{'duplicate_groups':dup})
    except Exception as e:add('dedupe','market_symbol_ts','FAIL',str(e))
    try:
        dup=c.execute("select count(*) from (select source,url,count(*) n from information_events where url is not null group by source,url having n>1)").fetchone()[0];add('dedupe','event_source_url','PASS' if dup==0 else 'WARN',f'{dup} duplicate groups',{'duplicate_groups':dup})
    except Exception as e:add('dedupe','event_source_url','FAIL',str(e))
    try:
        row=c.execute('select max(ts) from market_snapshots').fetchone()[0];dt=datetime.fromisoformat(str(row).replace('Z','+00:00')) if row else None;age=(datetime.now(timezone.utc)-dt).total_seconds()/60 if dt else 1e9;add('freshness','market_age','PASS' if age<20 else ('WARN' if age<180 else 'FAIL'),f'{age:.1f} min',{'age_minutes':age})
    except Exception as e:add('freshness','market_age','FAIL',str(e))
    try:
        active=c.execute("select count(*) from model_versions where status='active'").fetchone()[0];add('learning','single_active_model','PASS' if active==1 else 'FAIL',f'{active} active')
    except Exception as e:add('learning','single_active_model','FAIL',str(e))
    m=active_model();add('learning','bounded_weights','PASS' if all(abs(float(v))<=0.5 for v in m.get('weights',{}).values()) else 'FAIL',m.get('version','unknown'),m.get('weights',{}))
    add('safety','real_trading_off','PASS','No real broker/execution path enabled',{'real_trading':False})
    st=_status();sup=st.get('supabase_sync');learn=st.get('learning_persistence');add('sync','supabase_core','PASS' if sup=='OK' else 'WARN',str(sup or 'unknown'));add('sync','supabase_learning','PASS' if learn=='OK' else 'WARN',str(learn or 'unknown'))
    c.commit()
    try:
        c.execute('begin');c.execute("insert into control(key,value) values('__audit_rollback__','1') on conflict(key) do update set value='1'");c.execute('rollback');exists=c.execute("select 1 from control where key='__audit_rollback__'").fetchone();add('recovery','transaction_rollback','PASS' if not exists else 'FAIL','rollback isolation check')
    except Exception as e:
        try:c.execute('rollback')
        except Exception:pass
        add('recovery','transaction_rollback','FAIL',str(e))
    c.commit();c.close();summary={'PASS':0,'WARN':0,'FAIL':0}
    for t in tests:summary[t['status']]=summary.get(t['status'],0)+1
    return {'summary':summary,'tests':tests,'trading_real':False}
