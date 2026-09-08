import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

PC_SYNC_VERSION = '1.4.0'
CLOUD_BASE = 'https://radar-cloud-production.up.railway.app'


def _data_dir():
    return os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'InvestmentIntelligenceRadarData')

def _read_json(path, default=None):
    try:
        with open(path,'r',encoding='utf-8') as f:value=json.load(f)
        return value if isinstance(value,dict) else (default or {})
    except Exception:return default or {}

def _write_json_atomic(path,value):
    try:
        os.makedirs(os.path.dirname(path),exist_ok=True);tmp=path+'.tmp'
        with open(tmp,'w',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
        os.replace(tmp,path)
    except Exception:pass

def _get(path,timeout=20):
    req=urllib.request.Request(CLOUD_BASE+path,headers={'User-Agent':'InvestmentIntelligenceRadarDesktopSync/'+PC_SYNC_VERSION,'Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8'))

def _post(token,payload,timeout=35):
    data=json.dumps(payload,ensure_ascii=False).encode('utf-8');req=urllib.request.Request(CLOUD_BASE+'/pc-sync',data=data,method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','User-Agent':'InvestmentIntelligenceRadarDesktopSync/'+PC_SYNC_VERSION})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8'))

def _pull_cloud_cache():
    cache_path=os.path.join(_data_dir(),'cloud_intelligence_cache.json')
    try:
        snapshot=_get('/snapshot');learning=_get('/dashboard-v2');notifications=_get('/notifications')
        payload={'fetched_at':time.time(),'snapshot':snapshot,'learning':learning,'notifications':notifications,'sync_health':{'cloud':True,'learning_model':(learning.get('model') or {}).get('version'),'trading_real':False}}
        _write_json_atomic(cache_path,payload);return payload
    except Exception as exc:
        old=_read_json(cache_path);old['last_pull_error']=str(exc)[:500];old['last_pull_attempt']=time.time();_write_json_atomic(cache_path,old);return old

def _sync_once():
    from radar_core import con, init_db
    data_dir=_data_dir();settings_path=os.path.join(data_dir,'desktop_settings.json');state_path=os.path.join(data_dir,'pc_sync_state.json')
    settings=_read_json(settings_path);token=str(settings.get('cloud_control_token') or '').strip();node_id=str(settings.get('node_id') or '').strip();cloud_cache=_pull_cloud_cache()
    if not token or not node_id:return {'enabled':False,'reason':'waiting_for_cloud_control','cloud_pull':bool(cloud_cache)}
    state=_read_json(state_path,{'market_id':0,'event_id':0,'run_id':0});market_after=int(state.get('market_id') or 0);event_after=int(state.get('event_id') or 0);run_after=int(state.get('run_id') or 0)
    init_db();c=con()
    try:
        market=c.execute('select id,ts,symbol,price,volume,source from market_snapshots where id>? order by id limit 300',(market_after,)).fetchall();events=c.execute('select id,ts,source,title,url,category from information_events where id>? order by id limit 300',(event_after,)).fetchall();runs=c.execute('select id,ts,job,status,detail from system_runs where id>? order by id limit 300',(run_after,)).fetchall()
    finally:c.close()
    payload={'node_id':node_id,'name':os.environ.get('COMPUTERNAME','Windows PC'),'app_version':PC_SYNC_VERSION,'capabilities':['local-collector','paper-simulator','desktop-ui','persistent-sync','cloud-cache','intelligence-v2'],
      'market_snapshots':[{'id':r[0],'origin_id':r[0],'origin_node':node_id,'ts':r[1],'symbol':r[2],'price':r[3],'volume':r[4],'source':r[5]} for r in market],
      'information_events':[{'id':r[0],'origin_id':r[0],'origin_node':node_id,'ts':r[1],'source':r[2],'title':r[3],'url':r[4],'category':r[5]} for r in events],
      'system_runs':[{'id':r[0],'origin_id':r[0],'origin_node':node_id,'ts':r[1],'node_id':node_id,'kind':r[2],'status':r[3],'message':r[4]} for r in runs]}
    result=_post(token,payload)
    if not result.get('ok'):raise RuntimeError(str(result.get('error') or 'PC sync rejected'))
    if market:state['market_id']=market[-1][0]
    if events:state['event_id']=events[-1][0]
    if runs:state['run_id']=runs[-1][0]
    state['last_success']=time.time();state['last_error']='';state['last_counts']={'market':len(market),'events':len(events),'runs':len(runs)};state['cloud_cache_fetched_at']=cloud_cache.get('fetched_at');_write_json_atomic(state_path,state);return {'enabled':True,**state['last_counts']}

def _loop():
    time.sleep(8)
    while True:
        try:_sync_once()
        except urllib.error.HTTPError as exc:
            p=os.path.join(_data_dir(),'pc_sync_state.json');s=_read_json(p);s['last_error']='HTTP '+str(exc.code);s['last_attempt']=time.time();_write_json_atomic(p,s)
        except Exception as exc:
            p=os.path.join(_data_dir(),'pc_sync_state.json');s=_read_json(p);s['last_error']=str(exc)[:500];s['last_attempt']=time.time();_write_json_atomic(p,s)
        time.sleep(60)

def _install_native_panel():
    if os.name!='nt':return
    for _ in range(120):
        time.sleep(.5);m=sys.modules.get('__main__');root=getattr(m,'root',None) if m else None;main=getattr(m,'main',None) if m else None
        if root is not None and main is not None:
            def build():
                try:
                    import tkinter as tk
                    bg=getattr(m,'BG','#0f172a');panel=getattr(m,'PANEL','#1e293b');panel2=getattr(m,'PANEL2','#111827');text=getattr(m,'TEXT','#f8fafc');muted=getattr(m,'MUTED','#94a3b8');border=getattr(m,'BORDER','#334155');green=getattr(m,'GREEN','#16a34a');red=getattr(m,'RED','#dc2626');cyan=getattr(m,'CYAN','#22d3ee')
                    box=tk.Frame(main,bg=panel,highlightthickness=1,highlightbackground=border,padx=14,pady=12);box.pack(fill='x',pady=(0,10))
                    tk.Label(box,text='Brain Evolution v3 · aprendizaje y sincronización',bg=panel,fg=text,font=('Segoe UI',11,'bold')).pack(anchor='w')
                    status=tk.StringVar(value='Cargando estado central…');detail=tk.StringVar(value='')
                    tk.Label(box,textvariable=status,bg=panel,fg=cyan,font=('Segoe UI',9,'bold')).pack(anchor='w',pady=(4,0));tk.Label(box,textvariable=detail,bg=panel,fg=muted,font=('Segoe UI',8),justify='left',wraplength=1080).pack(anchor='w',pady=(2,0))
                    def refresh():
                        cache=_read_json(os.path.join(_data_dir(),'cloud_intelligence_cache.json'));sync=_read_json(os.path.join(_data_dir(),'pc_sync_state.json'));learning=cache.get('learning') or {};model=learning.get('model') or {};reg=learning.get('regime') or {};counts=learning.get('counts') or {};brain=learning.get('brain_evolution') or {};last=sync.get('last_success');age=(time.time()-last) if last else 1e9;ok=age<180 and not sync.get('last_error');status.set(('SINCRONIZACIÓN OK · ' if ok else 'REVISAR SINCRONIZACIÓN · ')+f"champion {model.get('version','—')} · generación {brain.get('current_generation','—')}");detail.set(f"Shadow {brain.get('shadow_champions',0)} · historical {brain.get('challengers_tested',0)} candidatos · live N {sum((x.get('n_live') or 0) for x in brain.get('transfer',[]))} · confianza {brain.get('ensemble_confidence',0):.2f} · sync {'OK' if ok else 'pendiente'} · REAL TRADING OFF")
                        try:root.after(10000,refresh)
                        except Exception:pass
                    refresh()
                except Exception:pass
            try:root.after(0,build)
            except Exception:pass
            return

if os.name=='nt':
    threading.Thread(target=_loop,name='radar-pc-bidirectional-sync',daemon=True).start()
    threading.Thread(target=_install_native_panel,name='radar-intelligence-v2-ui',daemon=True).start()
