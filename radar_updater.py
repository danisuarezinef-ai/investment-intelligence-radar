import os, sys, json, hashlib, tempfile, urllib.request, zipfile, shutil, subprocess, time
import tkinter as tk
APP_NAME='Investment Intelligence Radar'; UPDATE_MANIFEST='https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/updates/update_manifest.json'; APPDIR=os.path.dirname(os.path.abspath(sys.executable if getattr(sys,'frozen',False) else __file__)); DATA=os.path.join(os.environ.get('LOCALAPPDATA',os.path.expanduser('~')),'InvestmentIntelligenceRadarData'); VERSION_FILE=os.path.join(APPDIR,'version.json'); PID_FILE=os.path.join(DATA,'worker.pid')
BG='#0f172a'; PANEL='#1e293b'; PANEL2='#111827'; TEXT='#f8fafc'; MUTED='#94a3b8'; BLUE='#2563eb'; GREEN='#16a34a'; RED='#dc2626'; AMBER='#f59e0b'; BORDER='#334155'; CYAN='#22d3ee'
def _version_tuple(v):
    p=[]
    for x in str(v).split('.'):
        try:p.append(int(x))
        except:p.append(0)
    return tuple((p+[0,0,0])[:3])
def current_version():
    try:return json.load(open(VERSION_FILE,'r',encoding='utf-8-sig')).get('version','0.0.0')
    except:return '0.0.0'
def get_json(url,timeout=15):
    req=urllib.request.Request(url,headers={'User-Agent':'InvestmentIntelligenceRadarUpdater/1.2','Cache-Control':'no-cache'}); return json.loads(urllib.request.urlopen(req,timeout=timeout).read().decode('utf-8-sig'))
def sha256(path):
    h=hashlib.sha256(); f=open(path,'rb')
    for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    f.close(); return h.hexdigest()
def stop_worker():
    try:
        if os.path.exists(PID_FILE):subprocess.run(['taskkill','/PID',open(PID_FILE).read().strip(),'/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
    except:pass
    try:os.remove(PID_FILE)
    except:pass
def radar_dialog(root,title,message,kind='info',confirm=False):
    win=tk.Toplevel(root); win.title(title); win.configure(bg=BG); win.geometry('590x330'); win.resizable(False,False); win.grab_set(); outer=tk.Frame(win,bg=BG,padx=24,pady=22); outer.pack(fill='both',expand=True); card=tk.Frame(outer,bg=PANEL,highlightthickness=1,highlightbackground=BORDER,padx=24,pady=22); card.pack(fill='both',expand=True); accent={'info':GREEN,'warning':AMBER,'error':RED}.get(kind,CYAN)
    tk.Label(card,text='INVESTMENT INTELLIGENCE RADAR',bg=PANEL,fg=MUTED,font=('Segoe UI',8,'bold')).pack(anchor='w'); tk.Label(card,text=title,bg=PANEL,fg=accent,font=('Segoe UI',18,'bold')).pack(anchor='w',pady=(6,0)); tk.Frame(card,bg=accent,height=2).pack(fill='x',pady=(10,14)); tk.Label(card,text=message,bg=PANEL,fg=TEXT,font=('Segoe UI',10),justify='left',wraplength=500).pack(anchor='w'); result={'v':False}; buttons=tk.Frame(card,bg=PANEL); buttons.pack(side='bottom',fill='x',pady=(16,0))
    def close(v):result['v']=v; win.destroy()
    if confirm:tk.Button(buttons,text='AHORA NO',command=lambda:close(False),bg=PANEL2,fg=TEXT,relief='flat',bd=0,padx=18,pady=10).pack(side='right',padx=(8,0)); tk.Button(buttons,text='INSTALAR ACTUALIZACIÓN',command=lambda:close(True),bg=BLUE,fg='white',relief='flat',bd=0,padx=18,pady=10).pack(side='right')
    else:tk.Button(buttons,text='ACEPTAR',command=lambda:close(True),bg=BLUE,fg='white',relief='flat',bd=0,padx=20,pady=10).pack(side='right')
    win.protocol('WM_DELETE_WINDOW',lambda:close(False)); root.wait_window(win); return result['v']
def atomic_install(extract,new_version):
    targets=[]
    for name in ('InvestmentIntelligenceRadar.exe','RadarWorker.exe'):
        src=os.path.join(extract,name)
        if not os.path.isfile(src):raise RuntimeError('Falta '+name+' en el paquete.')
        targets.append((name,src))
    updater=os.path.join(extract,'RadarUpdater.exe')
    if os.path.isfile(updater):
        # Cannot overwrite the running updater directly. Stage it for the app to install on next launch.
        staged=os.path.join(DATA,'RadarUpdater.next.exe'); shutil.copy2(updater,staged)
    backup=os.path.join(DATA,'update_backup'); os.makedirs(backup,exist_ok=True); restored=[]
    try:
        for name,src in targets:
            dst=os.path.join(APPDIR,name); bak=os.path.join(backup,name+'.bak')
            if os.path.exists(dst):shutil.copy2(dst,bak)
            tmp=dst+'.new'; shutil.copy2(src,tmp); os.replace(tmp,dst); restored.append((dst,bak))
        json.dump({'version':new_version,'channel':'stable'},open(VERSION_FILE+'.new','w',encoding='utf-8'),ensure_ascii=False,indent=2); os.replace(VERSION_FILE+'.new',VERSION_FILE)
    except:
        for dst,bak in reversed(restored):
            try:
                if os.path.exists(bak):shutil.copy2(bak,dst)
            except:pass
        raise
def launch_app():
    exe=os.path.join(APPDIR,'InvestmentIntelligenceRadar.exe')
    if os.path.exists(exe):subprocess.Popen([exe],cwd=APPDIR,creationflags=0x08000000)
def main():
    root=tk.Tk(); root.withdraw(); cur=current_version()
    try:manifest=get_json(UPDATE_MANIFEST)
    except Exception as e:radar_dialog(root,'No se pudo comprobar la actualización',str(e),'error'); return 2
    latest=str(manifest.get('version','0.0.0'))
    if _version_tuple(latest)<=_version_tuple(cur):radar_dialog(root,'Radar está actualizado',f'Versión instalada: {cur}\n\nNo hay una versión más reciente en el canal estable.','info'); return 0
    notes=str(manifest.get('notes','')).strip(); text=f'Nueva versión: {latest}\nVersión instalada: {cur}' + (('\n\n'+notes) if notes else '') + '\n\nLa actualización conserva la base de datos y la configuración.'
    if not radar_dialog(root,'Actualización disponible',text,'warning',True):return 0
    package_url=manifest.get('package_url'); expected=str(manifest.get('sha256','')).lower().strip(); temp=tempfile.mkdtemp(prefix='radar_update_'); pkg=os.path.join(temp,'RadarUpdate.zip')
    try:
        req=urllib.request.Request(package_url,headers={'User-Agent':'InvestmentIntelligenceRadarUpdater/1.2','Cache-Control':'no-cache'}); shutil.copyfileobj(urllib.request.urlopen(req,timeout=60),open(pkg,'wb'))
        if sha256(pkg).lower()!=expected:raise RuntimeError('La firma SHA-256 no coincide.')
        extract=os.path.join(temp,'payload'); os.makedirs(extract,exist_ok=True); zipfile.ZipFile(pkg).extractall(extract); stop_worker(); time.sleep(1.5); atomic_install(extract,latest); radar_dialog(root,'Actualización completada',f'Radar se ha actualizado correctamente a la versión {latest}.\n\nLa aplicación volverá a abrirse ahora.','info'); launch_app(); return 0
    except Exception as e:radar_dialog(root,'Actualización cancelada','La instalación anterior se conserva.\n\n'+str(e),'error'); return 4
    finally:shutil.rmtree(temp,ignore_errors=True)
if __name__=='__main__':raise SystemExit(main())
