import os, sys, json, subprocess, urllib.request, urllib.error
import tkinter as tk
from radar_core import init_db, stats, STATUS, PID, DATA

APP_VERSION='1.1.1'
APPDIR=os.path.dirname(os.path.abspath(sys.executable if getattr(sys,'frozen',False) else __file__))
SETTINGS=os.path.join(DATA,'desktop_settings.json')
CLOUD_BASE='https://radar-cloud-production.up.railway.app'
worker_proc=None

BG='#0f172a'; PANEL='#1e293b'; PANEL2='#111827'; TEXT='#f8fafc'; MUTED='#94a3b8'
GREEN='#16a34a'; RED='#dc2626'; BLUE='#2563eb'; BORDER='#334155'; AMBER='#f59e0b'


def load_settings():
    try:
        if os.path.exists(SETTINGS):
            with open(SETTINGS,'r',encoding='utf-8') as f: return json.load(f)
    except Exception: pass
    return {}


def save_settings(d):
    try:
        os.makedirs(DATA,exist_ok=True)
        with open(SETTINGS,'w',encoding='utf-8') as f: json.dump(d,f,ensure_ascii=False,indent=2)
    except Exception: pass


def styled_dialog(title,message,kind='info',ask=False,secret=False):
    win=tk.Toplevel(root); win.title(title); win.configure(bg=BG); win.resizable(False,False); win.transient(root); win.grab_set()
    win.geometry('520x250')
    outer=tk.Frame(win,bg=BG,padx=22,pady=20); outer.pack(fill='both',expand=True)
    card=tk.Frame(outer,bg=PANEL,highlightthickness=1,highlightbackground=BORDER,padx=20,pady=18); card.pack(fill='both',expand=True)
    accent=GREEN if kind=='info' else (AMBER if kind=='ask' else RED)
    tk.Label(card,text=title,bg=PANEL,fg=accent,font=('Segoe UI',15,'bold')).pack(anchor='w')
    tk.Label(card,text=message,bg=PANEL,fg=TEXT,font=('Segoe UI',10),justify='left',wraplength=440).pack(anchor='w',pady=(12,12))
    result={'value':None}
    entry=None
    if secret:
        entry=tk.Entry(card,show='•',bg=PANEL2,fg=TEXT,insertbackground=TEXT,relief='flat',font=('Segoe UI',11))
        entry.pack(fill='x',ipady=8,pady=(0,14)); entry.focus_set()
    buttons=tk.Frame(card,bg=PANEL); buttons.pack(fill='x')
    def finish(v):
        result['value']=entry.get().strip() if secret and v else v
        win.destroy()
    if ask:
        tk.Button(buttons,text='CANCELAR',command=lambda:finish(False),bg=PANEL2,fg=TEXT,activebackground=PANEL2,activeforeground=TEXT,relief='flat',bd=0,padx=16,pady=8).pack(side='right',padx=(8,0))
        tk.Button(buttons,text='ACEPTAR',command=lambda:finish(True),bg=BLUE,fg='white',activebackground=BLUE,activeforeground='white',relief='flat',bd=0,padx=16,pady=8).pack(side='right')
    else:
        tk.Button(buttons,text='ACEPTAR',command=lambda:finish(True),bg=BLUE,fg='white',activebackground=BLUE,activeforeground='white',relief='flat',bd=0,padx=16,pady=8).pack(side='right')
    win.protocol('WM_DELETE_WINDOW',lambda:finish(False)); root.wait_window(win); return result['value']


def pid_running(pid):
    if os.name=='nt':
        import ctypes
        h=ctypes.windll.kernel32.OpenProcess(0x1000,False,pid)
        if h: ctypes.windll.kernel32.CloseHandle(h); return True
        return False
    try: os.kill(pid,0); return True
    except OSError: return False


def running():
    try: return os.path.exists(PID) and pid_running(int(open(PID).read().strip()))
    except Exception: return False


def start_worker():
    global worker_proc
    if running(): return
    exe=os.path.join(APPDIR,'RadarWorker.exe'); flags=0x08000000 if os.name=='nt' else 0
    if os.path.exists(exe): worker_proc=subprocess.Popen([exe],cwd=APPDIR,creationflags=flags)
    else: worker_proc=subprocess.Popen([sys.executable,os.path.join(os.path.dirname(__file__),'run_worker.py')],cwd=os.path.dirname(__file__),creationflags=flags)


def stop_worker():
    try:
        pid=int(open(PID).read().strip())
        if os.name=='nt': subprocess.run(['taskkill','/PID',str(pid),'/F'],creationflags=0x08000000,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else: os.kill(pid,15)
    except Exception: pass
    try: os.remove(PID)
    except OSError: pass


def cloud_get(path,timeout=5):
    req=urllib.request.Request(CLOUD_BASE+path,headers={'User-Agent':'InvestmentIntelligenceRadarDesktop/1.1'})
    with urllib.request.urlopen(req,timeout=timeout) as r: return json.loads(r.read().decode('utf-8'))


def cloud_toggle():
    settings=load_settings(); token=settings.get('cloud_control_token','').strip()
    if not token:
        token=styled_dialog('Conectar control Cloud','Introduce la clave de control Cloud. Se guardará en este ordenador y no volverá a pedirse.',kind='ask',ask=True,secret=True)
        if not token: return
        settings['cloud_control_token']=token.strip(); save_settings(settings); token=token.strip()
    try:
        req=urllib.request.Request(CLOUD_BASE+'/toggle',method='POST',headers={'Authorization':'Bearer '+token,'User-Agent':'InvestmentIntelligenceRadarDesktop/1.1'})
        with urllib.request.urlopen(req,timeout=8) as r: json.loads(r.read().decode('utf-8'))
        refresh_cloud()
    except urllib.error.HTTPError as e:
        if e.code==401:
            settings.pop('cloud_control_token',None); save_settings(settings)
            styled_dialog('Cloud','Clave de control incorrecta. Se ha borrado para volver a introducirla.',kind='error')
        else: styled_dialog('Cloud',f'Error HTTP {e.code}',kind='error')
    except Exception as e:
        styled_dialog('Cloud','No se pudo contactar con el servicio Cloud:\n'+str(e),kind='error')


def launch_updater():
    exe=os.path.join(APPDIR,'RadarUpdater.exe')
    if not os.path.exists(exe):
        styled_dialog('Actualizaciones','El actualizador no está disponible en esta instalación.',kind='error'); return
    try:
        subprocess.Popen([exe],cwd=APPDIR,creationflags=0x08000000 if os.name=='nt' else 0)
        root.after(600,root.destroy)
    except Exception as e: styled_dialog('Actualizaciones','No se pudo abrir el actualizador:\n'+str(e),kind='error')


init_db()
root=tk.Tk(); root.title('Investment Intelligence Radar'); root.geometry('1220x840'); root.minsize(1080,720); root.configure(bg=BG)
main=tk.Frame(root,bg=BG,padx=28,pady=24); main.pack(fill='both',expand=True)
header=tk.Frame(main,bg=BG); header.pack(fill='x')
header_left=tk.Frame(header,bg=BG); header_left.pack(side='left',fill='x',expand=True)
tk.Label(header_left,text='Investment Intelligence Radar',bg=BG,fg=TEXT,font=('Segoe UI',24,'bold')).pack(anchor='w')
tk.Label(header_left,text=f'Centro de control · Windows Desktop v{APP_VERSION} · actualizaciones integradas',bg=BG,fg=MUTED,font=('Segoe UI',10)).pack(anchor='w',pady=(2,18))
update_btn=tk.Button(header,text='BUSCAR ACTUALIZACIÓN',command=launch_updater,font=('Segoe UI',9,'bold'),fg='white',bg=BLUE,activebackground=BLUE,activeforeground='white',relief='flat',bd=0,padx=16,pady=9,cursor='hand2'); update_btn.pack(side='right',anchor='n',pady=(2,0))
controls=tk.Frame(main,bg=BG); controls.pack(fill='x')

def control_card(parent,title,subtitle):
    f=tk.Frame(parent,bg=PANEL,highlightthickness=1,highlightbackground=BORDER,padx=20,pady=18)
    tk.Label(f,text=title,bg=PANEL,fg=TEXT,font=('Segoe UI',15,'bold')).pack(anchor='w')
    state=tk.Label(f,text='COMPROBANDO',bg=PANEL,fg=AMBER,font=('Segoe UI',12,'bold')); state.pack(anchor='w',pady=(5,2))
    detail=tk.Label(f,text=subtitle,bg=PANEL,fg=MUTED,font=('Segoe UI',9),justify='left',wraplength=420); detail.pack(anchor='w')
    button=tk.Button(f,text='ON',font=('Segoe UI',11,'bold'),fg='white',bg=GREEN,activebackground=GREEN,activeforeground='white',relief='flat',bd=0,padx=24,pady=10,cursor='hand2'); button.pack(anchor='e',pady=(14,0))
    return f,state,detail,button

pc_card,pc_state,pc_detail,pc_btn=control_card(controls,'Actividad en este ordenador','Motor local: recopila datos y acelera el Radar cuando el PC está encendido.'); pc_card.pack(side='left',fill='both',expand=True,padx=(0,7))
cloud_card,cloud_state,cloud_detail,cloud_btn=control_card(controls,'Actividad continua en Cloud','Motor 24/7: sigue trabajando aunque este ordenador esté apagado.'); cloud_card.pack(side='left',fill='both',expand=True,padx=(7,0))

metrics=tk.Frame(main,bg=BG); metrics.pack(fill='x',pady=14)
metric_vars={k:tk.StringVar(value='—') for k in ['db','last','runs','prices','events','cloud']}
metric_defs=[('Base de datos','db'),('Último ciclo','last'),('Ejecuciones PC','runs'),('Mercado PC','prices'),('Eventos PC','events'),('Cloud','cloud')]
for i,(title,key) in enumerate(metric_defs):
    f=tk.Frame(metrics,bg=PANEL2,highlightthickness=1,highlightbackground=BORDER,padx=14,pady=12); f.grid(row=0,column=i,sticky='nsew',padx=(0 if i==0 else 4,0 if i==len(metric_defs)-1 else 4)); metrics.grid_columnconfigure(i,weight=1)
    tk.Label(f,text=title,bg=PANEL2,fg=MUTED,font=('Segoe UI',9)).pack(anchor='w'); tk.Label(f,textvariable=metric_vars[key],bg=PANEL2,fg=TEXT,font=('Segoe UI',15,'bold')).pack(anchor='w',pady=(4,0))

cloud_metrics=tk.Frame(main,bg=PANEL,highlightthickness=1,highlightbackground=BORDER,padx=16,pady=12); cloud_metrics.pack(fill='x',pady=(0,14))
tk.Label(cloud_metrics,text='Actividad Cloud verificada',bg=PANEL,fg=TEXT,font=('Segoe UI',11,'bold')).pack(side='left')
cloud_counts=tk.StringVar(value='Mercado —   ·   Eventos —   ·   Ciclos —')
tk.Label(cloud_metrics,textvariable=cloud_counts,bg=PANEL,fg=MUTED,font=('Segoe UI',10)).pack(side='right')

body=tk.Frame(main,bg=BG); body.pack(fill='both',expand=True)
left=tk.Frame(body,bg=PANEL,highlightthickness=1,highlightbackground=BORDER,padx=14,pady=12); left.pack(side='left',fill='both',expand=True,padx=(0,7))
right=tk.Frame(body,bg=PANEL,highlightthickness=1,highlightbackground=BORDER,padx=14,pady=12); right.pack(side='left',fill='both',expand=True,padx=(7,0))
tk.Label(left,text='Últimos precios · PC local',bg=PANEL,fg=TEXT,font=('Segoe UI',12,'bold')).pack(anchor='w',pady=(0,8)); tk.Label(right,text='Últimos eventos · PC local',bg=PANEL,fg=TEXT,font=('Segoe UI',12,'bold')).pack(anchor='w',pady=(0,8))
prices=tk.Listbox(left,bg=PANEL2,fg=TEXT,selectbackground=BLUE,selectforeground='white',highlightthickness=0,bd=0,font=('Consolas',10)); prices.pack(fill='both',expand=True)
events=tk.Listbox(right,bg=PANEL2,fg=TEXT,selectbackground=BLUE,selectforeground='white',highlightthickness=0,bd=0,font=('Segoe UI',9)); events.pack(fill='both',expand=True)
footer=tk.Label(main,text='Fuentes activas: Stooq · SEC EDGAR · Europe PMC   |   Trading real: OFF   |   Canal: estable',bg=BG,fg=MUTED,font=('Segoe UI',9)); footer.pack(anchor='w',pady=(12,0))

def toggle_pc():
    if running(): stop_worker()
    else: start_worker()
    root.after(700,refresh_local)

def refresh_local():
    r=running(); pc_btn.configure(text='OFF' if r else 'ON',bg=RED if r else GREEN,activebackground=RED if r else GREEN); pc_state.configure(text='ACTIVO' if r else 'DETENIDO',fg='#4ade80' if r else '#f87171')
    try:
        p,e,rr,latest,news=stats(); metric_vars['db'].set('CONECTADA'); metric_vars['prices'].set(str(p)); metric_vars['events'].set(str(e)); metric_vars['runs'].set(str(rr))
        status={}
        try:
            if os.path.exists(STATUS): status=json.load(open(STATUS,'r',encoding='utf-8'))
        except Exception: pass
        metric_vars['last'].set((status.get('last_job') or status.get('state') or '—')[:18])
        detail=status.get('last_detail','') or ('Motor local activo.' if r else 'Motor local detenido.')
        pc_detail.configure(text=detail[:180])
        prices.delete(0,'end'); [prices.insert('end',f'  {sym:<7} {price:>12.4f}    {source}') for sym,price,source,ts in latest]
        events.delete(0,'end'); [events.insert('end',f'  [{source}] {title}') for source,title,ts in news]
    except Exception as ex: metric_vars['db'].set('ERROR'); pc_detail.configure(text='Error de lectura: '+str(ex))
    root.after(3000,refresh_local)

def refresh_cloud():
    try:
        d=cloud_get('/health'); enabled=bool(d.get('cloud_enabled',True)); cloud_state.configure(text='ACTIVO 24/7' if enabled else 'PAUSADO',fg='#4ade80' if enabled else '#f87171'); cloud_btn.configure(text='OFF' if enabled else 'ON',bg=RED if enabled else GREEN,activebackground=RED if enabled else GREEN); metric_vars['cloud'].set('ONLINE' if enabled else 'PAUSADO')
        snap=cloud_get('/snapshot'); c=snap.get('counts',{}); st=snap.get('status',{}); cloud_counts.set(f"Mercado {c.get('prices',0)}   ·   Eventos {c.get('events',0)}   ·   Ciclos {c.get('runs',0)}")
        last=st.get('last_detail') or st.get('last_job') or st.get('state') or 'Servicio disponible'
        cloud_detail.configure(text=('Cloud activo · '+str(last)) if enabled else 'Cloud pausado. Pulsa ON para reanudarlo.')
    except Exception as e:
        cloud_state.configure(text='SIN CONEXIÓN',fg='#f87171'); cloud_detail.configure(text='No se ha podido verificar Railway: '+str(e)[:120]); metric_vars['cloud'].set('OFFLINE'); cloud_counts.set('Mercado —   ·   Eventos —   ·   Ciclos —')
    root.after(5000,refresh_cloud)

pc_btn.configure(command=toggle_pc); cloud_btn.configure(command=cloud_toggle)
start_worker(); refresh_local(); refresh_cloud(); root.mainloop()
