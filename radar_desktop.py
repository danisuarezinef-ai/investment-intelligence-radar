import os, sys, json, subprocess
import tkinter as tk
from tkinter import ttk
from radar_core import init_db, stats, STATUS, PID

APPDIR=os.path.dirname(os.path.abspath(sys.executable if getattr(sys,'frozen',False) else __file__))
worker_proc=None

def pid_running(pid):
    if os.name=='nt':
        import ctypes
        h=ctypes.windll.kernel32.OpenProcess(0x1000,False,pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    try:
        os.kill(pid,0); return True
    except OSError:
        return False

def running():
    try:
        return os.path.exists(PID) and pid_running(int(open(PID).read().strip()))
    except Exception:
        return False

def start_worker():
    global worker_proc
    if running(): return
    exe=os.path.join(APPDIR,'RadarWorker.exe')
    flags=0x08000000 if os.name=='nt' else 0
    if os.path.exists(exe):
        worker_proc=subprocess.Popen([exe],cwd=APPDIR,creationflags=flags)
    else:
        worker_proc=subprocess.Popen([sys.executable,os.path.join(os.path.dirname(__file__),'run_worker.py')],cwd=os.path.dirname(__file__),creationflags=flags)

def stop_worker():
    try:
        pid=int(open(PID).read().strip())
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(pid),'/F'],creationflags=0x08000000,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:
            os.kill(pid,15)
    except Exception:
        pass
    try: os.remove(PID)
    except OSError: pass

init_db()
root=tk.Tk(); root.title('Investment Intelligence Radar'); root.geometry('1000x700'); root.minsize(900,620)
style=ttk.Style()
try: style.theme_use('vista')
except Exception: pass
main=ttk.Frame(root,padding=18); main.pack(fill='both',expand=True)
ttk.Label(main,text='Investment Intelligence Radar',font=('Segoe UI',22,'bold')).pack(anchor='w')
ttk.Label(main,text='Windows Desktop · v1.0.0',font=('Segoe UI',10)).pack(anchor='w',pady=(0,16))

control=ttk.LabelFrame(main,text='Actividad PC',padding=12); control.pack(fill='x')
state_var=tk.StringVar(value='COMPROBANDO'); detail_var=tk.StringVar(value='')
row=ttk.Frame(control); row.pack(fill='x')
ttk.Label(row,textvariable=state_var,font=('Segoe UI',14,'bold')).pack(side='left')
btn=ttk.Button(row,text='ON'); btn.pack(side='right')
ttk.Label(control,textvariable=detail_var).pack(anchor='w',pady=(7,0))

metrics=ttk.Frame(main); metrics.pack(fill='x',pady=14)
price_var=tk.StringVar(value='0'); event_var=tk.StringVar(value='0'); run_var=tk.StringVar(value='0')
for title,var in [('Precios guardados',price_var),('Eventos / ciencia',event_var),('Ciclos registrados',run_var)]:
    f=ttk.LabelFrame(metrics,text=title,padding=12); f.pack(side='left',fill='x',expand=True,padx=4)
    ttk.Label(f,textvariable=var,font=('Segoe UI',18,'bold')).pack()

body=ttk.Frame(main); body.pack(fill='both',expand=True)
left=ttk.LabelFrame(body,text='Últimos precios',padding=8); left.pack(side='left',fill='both',expand=True,padx=(0,5))
right=ttk.LabelFrame(body,text='Últimos eventos',padding=8); right.pack(side='left',fill='both',expand=True,padx=(5,0))
prices=tk.Listbox(left,font=('Consolas',10)); prices.pack(fill='both',expand=True)
events=tk.Listbox(right,font=('Segoe UI',9)); events.pack(fill='both',expand=True)
cloud=ttk.LabelFrame(main,text='Cloud 24/7',padding=10); cloud.pack(fill='x',pady=(12,0))
ttk.Label(cloud,text='PENDIENTE DE CONEXIÓN · el nodo PC funciona de forma independiente y está preparado para sincronización Cloud.').pack(anchor='w')

def toggle():
    if running(): stop_worker()
    else: start_worker()
    root.after(700,refresh)
btn.configure(command=toggle)

def refresh():
    r=running(); btn.configure(text='OFF' if r else 'ON')
    status={}
    try:
        if os.path.exists(STATUS): status=json.load(open(STATUS,'r',encoding='utf-8'))
    except Exception: pass
    state_var.set(status.get('state','ACTIVO' if r else 'PAUSADO') if r else 'PAUSADO')
    detail_var.set('Motor local activo. Pulsa OFF para detenerlo.' if r else 'Motor local detenido. Pulsa ON para iniciar recopilación real.')
    try:
        p,e,rr,latest,news=stats(); price_var.set(str(p)); event_var.set(str(e)); run_var.set(str(rr))
        prices.delete(0,'end')
        for sym,price,source,ts in latest: prices.insert('end',f'{sym:<7} {price:>12.4f}   {source}')
        events.delete(0,'end')
        for source,title,ts in news: events.insert('end',f'[{source}] {title}')
    except Exception as ex:
        detail_var.set('Error de lectura: '+str(ex))
    root.after(3000,refresh)

start_worker(); refresh(); root.mainloop()
