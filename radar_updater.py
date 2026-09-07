import os, sys, json, hashlib, tempfile, urllib.request, zipfile, shutil, subprocess, time
import tkinter as tk
from tkinter import messagebox

APP_NAME='Investment Intelligence Radar'
UPDATE_MANIFEST='https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/updates/update_manifest.json'
APPDIR=os.path.dirname(os.path.abspath(sys.executable if getattr(sys,'frozen',False) else __file__))
DATA=os.path.join(os.environ.get('LOCALAPPDATA',os.path.expanduser('~')),'InvestmentIntelligenceRadarData')
VERSION_FILE=os.path.join(APPDIR,'version.json')
PID_FILE=os.path.join(DATA,'worker.pid')


def _version_tuple(v):
    parts=[]
    for x in str(v).strip().split('.'):
        try: parts.append(int(x))
        except Exception: parts.append(0)
    return tuple((parts+[0,0,0])[:3])


def current_version():
    try:
        with open(VERSION_FILE,'r',encoding='utf-8') as f:
            return json.load(f).get('version','0.0.0')
    except Exception:
        return '0.0.0'


def get_json(url,timeout=15):
    req=urllib.request.Request(url,headers={'User-Agent':'InvestmentIntelligenceRadarUpdater/1.0','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def stop_worker():
    try:
        if os.path.exists(PID_FILE):
            pid=int(open(PID_FILE,'r',encoding='utf-8').read().strip())
            subprocess.run(['taskkill','/PID',str(pid),'/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
    except Exception: pass
    try: os.remove(PID_FILE)
    except OSError: pass


def wait_app_exit():
    # The desktop launches the updater and then closes itself. Give it time to release the executable.
    time.sleep(1.5)


def atomic_install(extract_dir,new_version):
    app_new=os.path.join(extract_dir,'InvestmentIntelligenceRadar.exe')
    worker_new=os.path.join(extract_dir,'RadarWorker.exe')
    if not (os.path.isfile(app_new) and os.path.isfile(worker_new)):
        raise RuntimeError('El paquete de actualización no contiene los ejecutables esperados.')
    backup=os.path.join(DATA,'update_backup')
    os.makedirs(backup,exist_ok=True)
    targets=[('InvestmentIntelligenceRadar.exe',app_new),('RadarWorker.exe',worker_new)]
    restored=[]
    try:
        for name,src in targets:
            dst=os.path.join(APPDIR,name)
            bak=os.path.join(backup,name+'.bak')
            if os.path.exists(dst):
                shutil.copy2(dst,bak)
            tmp=dst+'.new'
            shutil.copy2(src,tmp)
            os.replace(tmp,dst)
            restored.append((dst,bak))
        with open(VERSION_FILE+'.new','w',encoding='utf-8') as f:
            json.dump({'version':new_version,'channel':'stable'},f,ensure_ascii=False,indent=2)
        os.replace(VERSION_FILE+'.new',VERSION_FILE)
    except Exception:
        for dst,bak in reversed(restored):
            try:
                if os.path.exists(bak): shutil.copy2(bak,dst)
            except Exception: pass
        raise


def launch_app():
    exe=os.path.join(APPDIR,'InvestmentIntelligenceRadar.exe')
    if os.path.exists(exe):
        subprocess.Popen([exe],cwd=APPDIR,creationflags=0x08000000)


def main():
    root=tk.Tk(); root.withdraw()
    cur=current_version()
    try:
        manifest=get_json(UPDATE_MANIFEST)
    except Exception as e:
        messagebox.showerror('Actualizaciones',f'No se pudo comprobar si hay actualizaciones.\n\n{e}')
        return 2
    latest=str(manifest.get('version','0.0.0'))
    if _version_tuple(latest) <= _version_tuple(cur):
        messagebox.showinfo('Actualizaciones',f'Investment Intelligence Radar está actualizado.\n\nVersión instalada: {cur}')
        return 0
    notes=str(manifest.get('notes','')).strip()
    text=f'Nueva versión disponible: {latest}\nVersión instalada: {cur}'
    if notes: text+='\n\n'+notes
    text+='\n\n¿Instalar ahora?'
    if not messagebox.askyesno('Actualización disponible',text): return 0
    package_url=manifest.get('package_url')
    expected=str(manifest.get('sha256','')).lower().strip()
    if not package_url or not expected:
        messagebox.showerror('Actualizaciones','El manifiesto de actualización está incompleto.')
        return 3
    temp=tempfile.mkdtemp(prefix='radar_update_')
    pkg=os.path.join(temp,'RadarUpdate.zip')
    try:
        req=urllib.request.Request(package_url,headers={'User-Agent':'InvestmentIntelligenceRadarUpdater/1.0','Cache-Control':'no-cache'})
        with urllib.request.urlopen(req,timeout=60) as r, open(pkg,'wb') as f:
            shutil.copyfileobj(r,f)
        actual=sha256(pkg)
        if actual.lower()!=expected:
            raise RuntimeError('La firma SHA-256 del paquete no coincide. La actualización se ha cancelado.')
        extract=os.path.join(temp,'payload'); os.makedirs(extract,exist_ok=True)
        with zipfile.ZipFile(pkg,'r') as z: z.extractall(extract)
        stop_worker(); wait_app_exit(); atomic_install(extract,latest)
        messagebox.showinfo('Actualización completada',f'Investment Intelligence Radar se ha actualizado a la versión {latest}.')
        launch_app(); return 0
    except Exception as e:
        messagebox.showerror('Actualización cancelada',f'No se pudo completar la actualización. La instalación anterior se conserva.\n\n{e}')
        return 4
    finally:
        try: shutil.rmtree(temp,ignore_errors=True)
        except Exception: pass


if __name__=='__main__':
    raise SystemExit(main())
