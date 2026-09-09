import os, sys, json, hashlib, tempfile, urllib.request, zipfile, shutil, subprocess, time, traceback, threading
import tkinter as tk
from tkinter import ttk

APP='Radar de Inversión'
UPDATE_MANIFEST='https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/updates/update_manifest.json'
APPDIR=os.path.dirname(os.path.abspath(sys.executable if getattr(sys,'frozen',False) else __file__))
DATA=os.path.join(os.environ.get('LOCALAPPDATA',os.path.expanduser('~')),'InvestmentIntelligenceRadarData')
VERSION_FILE=os.path.join(APPDIR,'version.json')
LOG=os.path.join(DATA,'updater_v2.log')
PID_FILE=os.path.join(DATA,'worker.pid')
BG='#0f172a'; PANEL='#1e293b'; TEXT='#f8fafc'; MUTED='#94a3b8'; BLUE='#2563eb'; GREEN='#16a34a'; RED='#dc2626'; AMBER='#f59e0b'
PAYLOAD_BINARIES=('InvestmentIntelligenceRadar.exe','RadarSimulationLab.exe','RadarWorker.exe')
os.makedirs(DATA,exist_ok=True)

def log(s):
    try:
        with open(LOG,'a',encoding='utf-8') as f:f.write(time.strftime('%Y-%m-%d %H:%M:%S')+' '+str(s)+'\n')
    except:pass

def vt(v):
    a=[]
    for x in str(v).split('.'):
        try:a.append(int(x))
        except:a.append(0)
    return tuple((a+[0,0,0])[:3])

def curver():
    try:return json.load(open(VERSION_FILE,'r',encoding='utf-8-sig')).get('version','0.0.0')
    except:return '0.0.0'

def getjson(url):
    r=urllib.request.Request(url,headers={'User-Agent':'InvestmentIntelligenceRadarUpdater/2.1','Cache-Control':'no-cache'})
    return json.loads(urllib.request.urlopen(r,timeout=20).read().decode('utf-8-sig'))

def filehash(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest().lower()

def stop_processes():
    if os.name!='nt':return
    for name in ('RadarSimulationLab.exe','RadarWorker.exe','InvestmentIntelligenceRadar.exe'):
        try:subprocess.run(['taskkill','/F','/IM',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
        except:pass
    try:os.remove(PID_FILE)
    except:pass

def launch_app():
    exe=os.path.join(APPDIR,'InvestmentIntelligenceRadar.exe')
    if os.path.exists(exe):subprocess.Popen([exe],cwd=APPDIR,creationflags=0x08000000 if os.name=='nt' else 0)

def install(pkg,version):
    tmp=tempfile.mkdtemp(prefix='radar_update_')
    try:
        z=os.path.join(tmp,'payload'); os.makedirs(z,exist_ok=True); zipfile.ZipFile(pkg).extractall(z)
        for name in PAYLOAD_BINARIES:
            src=os.path.join(z,name)
            if not os.path.isfile(src):raise RuntimeError('Falta '+name+' en el paquete')
        stop_processes(); time.sleep(1.5)
        backup=os.path.join(DATA,'update_backup'); os.makedirs(backup,exist_ok=True)
        for name in PAYLOAD_BINARIES:
            src=os.path.join(z,name); dst=os.path.join(APPDIR,name)
            if os.path.exists(dst):shutil.copy2(dst,os.path.join(backup,name+'.bak'))
            new=dst+'.new'; shutil.copy2(src,new); os.replace(new,dst)
        up=os.path.join(z,'RadarUpdater.exe')
        if os.path.exists(up):shutil.copy2(up,os.path.join(DATA,'RadarUpdater.next.exe'))
        with open(VERSION_FILE+'.new','w',encoding='utf-8') as f:json.dump({'version':version,'channel':'stable'},f,indent=2)
        os.replace(VERSION_FILE+'.new',VERSION_FILE)
        log('installed '+version+' binaries='+','.join(PAYLOAD_BINARIES))
    finally:shutil.rmtree(tmp,ignore_errors=True)

def main():
    root=tk.Tk(); root.title('Radar de Inversión · Actualizador'); root.geometry('760x560'); root.minsize(640,500); root.configure(bg=BG)
    root.lift(); root.attributes('-topmost',True); root.after(1200,lambda:root.attributes('-topmost',False))
    frame=tk.Frame(root,bg=PANEL,padx=26,pady=24); frame.pack(fill='both',expand=True,padx=24,pady=24)
    title=tk.Label(frame,text='ACTUALIZADOR DE RADAR DE INVERSIÓN',bg=PANEL,fg=TEXT,font=('Segoe UI',16,'bold')); title.pack(anchor='w')
    status=tk.StringVar(value='Comprobando actualizaciones…')
    msg=tk.Label(frame,textvariable=status,bg=PANEL,fg=MUTED,font=('Segoe UI',10),justify='left',wraplength=650); msg.pack(anchor='w',fill='x',pady=(14,12))
    prog=ttk.Progressbar(frame,mode='indeterminate'); prog.pack(fill='x',pady=(0,16)); prog.start(12)
    buttons=tk.Frame(frame,bg=PANEL); buttons.pack(side='bottom',fill='x')
    def run():
        try:
            m=getjson(UPDATE_MANIFEST); rv=m.get('version','0.0.0'); cv=curver()
            if vt(rv)<=vt(cv):status.set(f'Radar de Inversión ya está actualizado (v{cv}).'); prog.stop(); return
            url=m.get('package_url'); expected=(m.get('sha256') or '').lower()
            if not url or not expected:raise RuntimeError('Manifest incompleto')
            status.set(f'Descargando Radar de Inversión v{rv}…'); root.update_idletasks()
            pkg=os.path.join(tempfile.gettempdir(),'RadarUpdate.zip')
            req=urllib.request.Request(url,headers={'User-Agent':'InvestmentIntelligenceRadarUpdater/2.1','Cache-Control':'no-cache'})
            with urllib.request.urlopen(req,timeout=60) as r, open(pkg,'wb') as f:shutil.copyfileobj(r,f)
            if filehash(pkg)!=expected:raise RuntimeError('La firma SHA-256 del paquete no coincide')
            status.set('Instalando aplicación, simulador y worker…'); root.update_idletasks(); install(pkg,rv)
            status.set(f'Radar de Inversión y Simulation Lab actualizados correctamente a v{rv}.'); prog.stop(); launch_app(); root.after(1000,root.destroy)
        except Exception as e:
            log(traceback.format_exc()); status.set('No se pudo actualizar:\n'+str(e)); prog.stop()
    threading.Thread(target=run,daemon=True).start(); root.mainloop()

if __name__=='__main__':main()
