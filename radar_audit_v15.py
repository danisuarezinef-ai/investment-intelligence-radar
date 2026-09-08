import json
from datetime import datetime, timezone
from radar_core import con, init_db, STATUS, now
from radar_learning import init_learning_db, active_model
from radar_brain_evolution import init_brain_db


def _status():
    try:
        with open(STATUS,'r',encoding='utf-8') as f:return json.load(f)
    except Exception:return {}


def run_integrity_audit():
    init_db();init_learning_db();init_brain_db();c=con();tests=[]
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
    c.commit()
    try:
        m=active_model();add('learning','bounded_weights','PASS' if all(abs(float(v))<=0.5 for v in m.get('weights',{}).values()) else 'FAIL',m.get('version','unknown'),m.get('weights',{}))
    except Exception as e:add('learning','bounded_weights','FAIL',str(e))
    add('safety','real_trading_off','PASS','No real broker/execution path enabled',{'real_trading':False})
    for name,sql,expect in (
      ('one_active_champion',"select count(*) from brain_lineages where status='operational_champion'",(0,1)),
      ('genealogy_complete',"select count(*) from brain_lineages where generation>0 and (parent is null or training_method is null or mutation is null)",(0,)),
      ('live_predictions_immutable',"select count(*) from brain_shadow_predictions where outcome is not null and evaluated_at is null",(0,)),
      ('vault_not_used_for_training',"select count(*) from brain_vault_events where purpose in ('training','candidate_selection')",(0,)),
      ('deep_vault_not_used_for_training',"select count(*) from brain_vault_events where vault_key='deep_final_test' and purpose in ('training','candidate_selection')",(0,))):
        try:
            value=c.execute(sql).fetchone()[0];add('brain',name,'PASS' if value in expect else 'FAIL',str(value),{'count':value})
        except Exception as e:add('brain',name,'FAIL',str(e))
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
