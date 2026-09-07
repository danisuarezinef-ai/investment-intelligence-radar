import os, sys, json, subprocess, urllib.request, urllib.error, threading
import tkinter as tk
from radar_core import init_db, stats, STATUS, PID, DATA, profitability_leaders, opportunity_rankings, paper_status, paper_start, paper_toggle

APP_VERSION='1.2.0'; APPDIR=os.path.dirname(os.path.abspath(sys.executable if getattr(sys,'frozen',False) else __file__))
SETTINGS=os.path.join(DATA,'desktop_settings.json'); CLOUD_BASE='https://radar-cloud-production.up.railway.app'; UPDATER_URL='https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/updates/RadarUpdater.exe'; worker_proc=None
BG='#0f172a'; PANEL='#1e293b'; PANEL2='#111827'; TEXT='#f8fafc'; MUTED='#94a3b8'; GREEN='#16a34a'; RED='#dc2626'; BLUE='#2563eb'; BORDER='#334155'; AMBER='#f59e0b'; CYAN='#22d3ee'

def load_settings():
    try:
        if os.path.exists(SETTINGS):return json.load(open(SETTINGS,'r',encoding='utf-8'))
    except:pass
    return {}
def save_settings(d):
    try:json.dump(d,open(SETTINGS,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    except:pass

def refresh_windows_shortcuts():
    if os.name!='nt' or not getattr(sys,'frozen',False):return
    exe=os.path.join(APPDIR,'InvestmentIntelligenceRadar.exe')
    try:
        ps=r'''$ErrorActionPreference='SilentlyContinue';$exe=$env:RADAR_EXE;$ws=New-Object -ComObject WScript.Shell;$desktop=[Environment]::GetFolderPath('Desktop');$start=Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs';foreach($path in @((Join-Path $desktop 'Investment Intelligence Radar.lnk'),(Join-Path $start 'Investment Intelligence Radar.lnk'))){if(Test-Path $path){Remove-Item $path -Force};$s=$ws.CreateShortcut($path);$s.TargetPath=$exe;$s.WorkingDirectory=Split-Path $exe;$s.IconLocation="$exe,0";$s.Description='Investment Intelligence Radar';$s.Save()}'''
        env=os.environ.copy(); env['RADAR_EXE']=exe; subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-Command',ps],env=env,creationflags=0x08000000,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
        import ctypes; ctypes.windll.shell32.SHChangeNotify(0x08000000,0,None,None)
    except:pass

def styled_dialog(title,message,kind='info',ask=False,secret=False):
    win=tk.Toplevel(root); win.title(title); win.configure(bg=BG); win.resizable(False,False); win.geometry('560x280'); win.transient(root); win.grab_set(); result={'v':None}
    outer=tk.Frame(win,bg=BG,padx=24,pady=22); outer.pack(fill='both',expand=True); card=tk.Frame(outer,bg=PANEL,highlightthickness=1,highlightbackground=BORDER,padx=22,pady=20); card.pack(fill='both',expand=True)
    accent={'info':GREEN,'ask':AMBER,'error':RED}.get(kind,BLUE); tk.Label(card,text=title,bg=PANEL,fg=accent,font=('Segoe UI',16,'bold')).pack(anchor='w'); tk.Label(card,text=message,bg=PANEL,fg=TEXT,font=('Segoe UI',10),justify='left',wraplength=470).pack(anchor='w',pady=(14,14))
    entry=None
    if secret:entry=tk.Entry(card,show='•',bg=PANEL2,fg=TEXT,insertbackground=TEXT,relief='flat',font=('Segoe UI',11)); entry.pack(fill='x',ipady=8,pady=(0,14)); entry.focus_set()
    buttons=tk.Frame(card,bg=PANEL); buttons.pack(side='bottom',fill='x')
    def close(v):result['v']=entry.get().strip() if secret and v else v; win.destroy()
    if ask:tk.Button(buttons,text='CANCELAR',command=lambda:close(False),bg=PANEL2,fg=TEXT,relief='flat',bd=0,padx=16,pady=8).pack(side='right',padx=(8,0))
    tk.Button(buttons,text='ACEPTAR',command=lambda:close(True),bg=BLUE,fg='white',relief='flat',bd=0,padx=16,pady=8).pack(side='right'); win.protocol('WM_DELETE_WINDOW',lambda:close(False)); root.wait_window(win); return result['v']

def pid_running(pid):
    if os.name=='nt':
        import ctypes; h=ctypes.windll.kernel32.OpenProcess(0x1000,False,pid)
        if h:ctypes.windll.kernel32.CloseHandle(h); return True
        return False
    try:os.kill(pid,0); return True
    except:return False
def running():
    try:return os.path.exists(PID) and pid_running(int(open(PID).read().strip()))
    except:return False
def start_worker():
    global worker_proc
    if running():return
    exe=os.path.join(APPDIR,'RadarWorker.exe'); flags=0x08000000 if os.name=='nt' else 0; worker_proc=subprocess.Popen([exe] if os.path.exists(exe) else [sys.executable,os.path.join(os.path.dirname(__file__),'run_worker.py')],cwd=APPDIR,creationflags=flags)
def stop_worker():
    try:
        pid=int(open(PID).read().strip()); subprocess.run(['taskkill','/PID',str(pid),'/F'],creationflags=0x08000000,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) if os.name=='nt' else os.kill(pid,15)
    except:pass
    try:os.remove(PID)
    except:pass

def cloud_get(path,timeout=6):
    req=urllib.request.Request(CLOUD_BASE+path,headers={'User-Agent':'InvestmentIntelligenceRadarDesktop/1.2'}); return json.loads(urllib.request.urlopen(req,timeout=timeout).read().decode('utf-8'))
def cloud_toggle():
    d=load_settings(); token=d.get('cloud_control_token','').strip()
    if not token:
        token=styled_dialog('Conectar control Cloud','Introduce la clave de control Cloud. Se guardará una sola vez en este ordenador.','ask',True,True)
        if not token:return
        d['cloud_control_token']=token; save_settings(d)
    try:
        req=urllib.request.Request(CLOUD_BASE+'/toggle',method='POST',headers={'Authorization':'Bearer '+token,'User-Agent':'InvestmentIntelligenceRadarDesktop/1.2'}); urllib.request.urlopen(req,timeout=8).read(); refresh_cloud()
    except urllib.error.HTTPError as e:styled_dialog('Cloud',f'Error HTTP {e.code}.','error')
    except Exception as e:styled_dialog('Cloud','No se pudo contactar con Cloud:\n'+str(e),'error')

def self_heal_updater():
    if os.name!='nt':return
    def job():
        try:
            req=urllib.request.Request(UPDATER_URL,headers={'User-Agent':'InvestmentIntelligenceRadarDesktop/1.2','Cache-Control':'no-cache'}); data=urllib.request.urlopen(req,timeout=30).read()
            if len(data)<100000 or data[:2]!=b'MZ':return
            dst=os.path.join(APPDIR,'RadarUpdater.exe'); tmp=dst+'.new'; open(tmp,'wb').write(data); os.replace(tmp,dst)
        except:pass
    threading.Thread(target=job,daemon=True).start()
def launch_updater():
    exe=os.path.join(APPDIR,'RadarUpdater.exe')
    if not os.path.exists(exe):styled_dialog('Actualizaciones','El actualizador todavía no está disponible.','error'); return
    subprocess.Popen([exe],cwd=APPDIR,creationflags=0x08000000 if os.name=='nt' else 0); root.after(600,root.destroy)

def toggle_pc():stop_worker() if running() else start_worker(); root.after(700,refresh_local)
def start_paper():paper_start(1000.0); refresh_investment()
def toggle_paper():paper_toggle(); refresh_investment()
def card(parent,title):
    f=tk.Frame(parent,bg=PANEL,highlightthickness=1,highlightbackground=BORDER,padx=16,pady=14); tk.Label(f,text=title,bg=PANEL,fg=TEXT,font=('Segoe UI',12,'bold')).pack(anchor='w',pady=(0,8)); return f
def set_list(box,items):box.delete(0,'end'); [box.insert('end',x) for x in items]

init_db(); refresh_windows_shortcuts(); root=tk.Tk(); root.title('Investment Intelligence Radar'); root.geometry('1280x940'); root.minsize(1160,820); root.configure(bg=BG)
main=tk.Frame(root,bg=BG,padx=24,pady=20); main.pack(fill='both',expand=True)
header=tk.Frame(main,bg=BG); header.pack(fill='x'); hleft=tk.Frame(header,bg=BG); hleft.pack(side='left',fill='x',expand=True)
tk.Label(hleft,text='Investment Intelligence Radar',bg=BG,fg=TEXT,font=('Segoe UI',24,'bold')).pack(anchor='w'); tk.Label(hleft,text=f'Inteligencia de inversión · Windows v{APP_VERSION} · Trading real OFF',bg=BG,fg=MUTED,font=('Segoe UI',10)).pack(anchor='w',pady=(2,14)); tk.Button(header,text='BUSCAR ACTUALIZACIÓN',command=launch_updater,bg=BLUE,fg='white',relief='flat',bd=0,padx=16,pady=9,font=('Segoe UI',9,'bold')).pack(side='right',anchor='n')
controls=tk.Frame(main,bg=BG); controls.pack(fill='x')
def control_card(parent,title,subtitle):
    f=card(parent,title); state=tk.Label(f,text='COMPROBANDO',bg=PANEL,fg=AMBER,font=('Segoe UI',12,'bold')); state.pack(anchor='w'); detail=tk.Label(f,text=subtitle,bg=PANEL,fg=MUTED,font=('Segoe UI',9),justify='left',wraplength=500); detail.pack(anchor='w',pady=(4,6)); b=tk.Button(f,text='ON',bg=GREEN,fg='white',relief='flat',bd=0,padx=22,pady=8,font=('Segoe UI',10,'bold')); b.pack(anchor='e'); return f,state,detail,b
pc_card,pc_state,pc_detail,pc_btn=control_card(controls,'Actividad en este ordenador','Motor local: recopila, analiza y acelera el Radar.'); pc_card.pack(side='left',fill='both',expand=True,padx=(0,6)); cloud_card,cloud_state,cloud_detail,cloud_btn=control_card(controls,'Actividad continua en Cloud','Motor 24/7: sigue trabajando con el PC apagado.'); cloud_card.pack(side='left',fill='both',expand=True,padx=(6,0)); pc_btn.configure(command=toggle_pc); cloud_btn.configure(command=cloud_toggle)
metrics=tk.Frame(main,bg=BG); metrics.pack(fill='x',pady=12); metric_vars={k:tk.StringVar(value='—') for k in ['db','prices','events','runs','cloud','paper']}
for i,(title,key) in enumerate([('Base de datos','db'),('Precios PC','prices'),('Eventos PC','events'),('Ciclos PC','runs'),('Cloud','cloud'),('Simulador','paper')]):
    f=tk.Frame(metrics,bg=PANEL2,highlightthickness=1,highlightbackground=BORDER,padx=12,pady=10); f.grid(row=0,column=i,sticky='nsew',padx=3); metrics.grid_columnconfigure(i,weight=1); tk.Label(f,text=title,bg=PANEL2,fg=MUTED,font=('Segoe UI',8)).pack(anchor='w'); tk.Label(f,textvariable=metric_vars[key],bg=PANEL2,fg=TEXT,font=('Segoe UI',14,'bold')).pack(anchor='w',pady=(3,0))
invest=tk.Frame(main,bg=BG); invest.pack(fill='x',pady=(0,12)); sim=card(invest,'Simulador autónomo · cartera ficticia'); sim.pack(side='left',fill='both',expand=True,padx=(0,6)); sim_value=tk.StringVar(value='No iniciado'); sim_detail=tk.StringVar(value='Carga 1.000 € ficticios y deja que Radar los gestione con riesgo limitado.'); tk.Label(sim,textvariable=sim_value,bg=PANEL,fg=CYAN,font=('Segoe UI',20,'bold')).pack(anchor='w'); tk.Label(sim,textvariable=sim_detail,bg=PANEL,fg=MUTED,font=('Segoe UI',9),justify='left',wraplength=540).pack(anchor='w',pady=(4,10)); sb=tk.Frame(sim,bg=PANEL); sb.pack(fill='x'); tk.Button(sb,text='CREAR SIMULACIÓN 1.000 €',command=start_paper,bg=BLUE,fg='white',relief='flat',bd=0,padx=14,pady=8).pack(side='left'); tk.Button(sb,text='PAUSAR / REANUDAR',command=toggle_paper,bg=PANEL2,fg=TEXT,relief='flat',bd=0,padx=14,pady=8).pack(side='left',padx=8)
cloudstrip=card(invest,'Actividad Cloud verificada'); cloudstrip.pack(side='left',fill='both',expand=True,padx=(6,0)); cloud_counts=tk.StringVar(value='Mercado — · Eventos — · Ciclos —'); tk.Label(cloudstrip,textvariable=cloud_counts,bg=PANEL,fg=CYAN,font=('Segoe UI',13,'bold')).pack(anchor='w'); tk.Label(cloudstrip,text='Los contadores deben crecer; “activo” por sí solo no basta.',bg=PANEL,fg=MUTED,font=('Segoe UI',9)).pack(anchor='w',pady=(6,0))
rankrow=tk.Frame(main,bg=BG); rankrow.pack(fill='both',expand=True); leaders=card(rankrow,'Más rentables según el histórico recopilado'); leaders.pack(side='left',fill='both',expand=True,padx=(0,5)); leader_box=tk.Listbox(leaders,bg=PANEL2,fg=TEXT,highlightthickness=0,bd=0,font=('Consolas',9),height=11); leader_box.pack(fill='both',expand=True); opps=card(rankrow,'Mejores inversiones potenciales · riesgo / retorno'); opps.pack(side='left',fill='both',expand=True,padx=(5,0)); opp_box=tk.Listbox(opps,bg=PANEL2,fg=TEXT,highlightthickness=0,bd=0,font=('Consolas',9),height=11); opp_box.pack(fill='both',expand=True)
feed=tk.Frame(main,bg=BG); feed.pack(fill='both',expand=True,pady=(12,0)); lf=card(feed,'Últimos precios · PC local'); lf.pack(side='left',fill='both',expand=True,padx=(0,5)); rf=card(feed,'Últimos eventos · PC local'); rf.pack(side='left',fill='both',expand=True,padx=(5,0)); prices=tk.Listbox(lf,bg=PANEL2,fg=TEXT,highlightthickness=0,bd=0,font=('Consolas',9),height=9); prices.pack(fill='both',expand=True); events=tk.Listbox(rf,bg=PANEL2,fg=TEXT,highlightthickness=0,bd=0,font=('Segoe UI',8),height=9); events.pack(fill='both',expand=True)

def refresh_local():
    r=running(); pc_state.configure(text='ACTIVO' if r else 'DETENIDO',fg='#4ade80' if r else '#f87171'); pc_btn.configure(text='OFF' if r else 'ON',bg=RED if r else GREEN)
    try:
        p,e,rr,latest,news=stats(); metric_vars['db'].set('CONECTADA'); metric_vars['prices'].set(str(p)); metric_vars['events'].set(str(e)); metric_vars['runs'].set(str(rr)); status={}
        try:status=json.load(open(STATUS,'r',encoding='utf-8')) if os.path.exists(STATUS) else {}
        except:pass
        pc_detail.configure(text=(status.get('last_detail') or ('Motor local activo.' if r else 'Motor local detenido.'))[:230]); set_list(prices,[f'  {s:<7} {pr:>11.4f}  {src}' for s,pr,src,ts in latest]); set_list(events,[f'  [{src}] {title}' for src,title,ts in news])
    except Exception as ex:metric_vars['db'].set('ERROR'); pc_detail.configure(text='Error de lectura: '+str(ex))
    root.after(3000,refresh_local)
def refresh_cloud():
    try:
        d=cloud_get('/health'); enabled=bool(d.get('cloud_enabled',True)); cloud_state.configure(text='ACTIVO 24/7' if enabled else 'PAUSADO',fg='#4ade80' if enabled else '#f87171'); cloud_btn.configure(text='OFF' if enabled else 'ON',bg=RED if enabled else GREEN); metric_vars['cloud'].set('ONLINE' if enabled else 'PAUSADO'); snap=cloud_get('/snapshot'); c=snap.get('counts',{}); st=snap.get('status',{}); cloud_counts.set(f"Mercado {c.get('prices',0)} · Eventos {c.get('events',0)} · Ciclos {c.get('runs',0)}"); cloud_detail.configure(text=('Cloud activo · '+str(st.get('last_detail') or st.get('state') or 'Servicio disponible'))[:230])
    except Exception as e:cloud_state.configure(text='SIN CONEXIÓN',fg='#f87171'); cloud_detail.configure(text='No se ha podido verificar Railway: '+str(e)[:160]); metric_vars['cloud'].set('OFFLINE')
    root.after(5000,refresh_cloud)
def refresh_investment():
    st=paper_status()
    if st.get('configured'):
        sim_value.set(f"{st['total']:.2f} €   ({st['pnl_pct']:+.2f}%)"); sim_detail.set(f"Inicial {st['initial']:.2f} € · Efectivo {st['cash']:.2f} € · Invertido {st.get('invested',0):.2f} € · {'AUTÓNOMO' if st['enabled'] else 'PAUSADO'}"); metric_vars['paper'].set(f"{st['total']:.0f} €")
    else:sim_value.set('No iniciado'); metric_vars['paper'].set('OFF')
    lines=[]
    for label,days in [('SEMANA',7),('MES',30),('AÑO',365)]:
        vals=profitability_leaders(days,3); lines.append('  '+label); lines += [f"    {x['symbol']:<7} {x['return_pct']:+7.2f}%" for x in vals] if vals else ['    Histórico insuficiente']
    set_list(leader_box,lines); ranks=opportunity_rankings(5); out=[]
    for key,label in [('bajo','RIESGO BAJO'),('intermedio','RIESGO INTERMEDIO'),('alto','RIESGO ALTO')]:
        out.append('  '+label); vals=ranks[key]; out += [f"    {x['symbol']:<7} score {x['score']:>6.2f}  mom7 {x['momentum7']:+6.2f}%" for x in vals] if vals else ['    Aún sin candidatos suficientes']
    set_list(opp_box,out); root.after(10000,refresh_investment)

start_worker(); self_heal_updater(); refresh_local(); refresh_cloud(); refresh_investment(); root.mainloop()
