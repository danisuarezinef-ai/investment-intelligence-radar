import os, sys, json, subprocess, urllib.request, urllib.error, threading, time, hashlib, uuid
import tkinter as tk

from radar_core import (
    init_db, stats, STATUS, PID, DATA, profitability_leaders, opportunity_rankings,
    paper_status, paper_start, paper_toggle, paper_step, history_ready, collect_history
)

APP_VERSION = '1.3.0'
APPDIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
SETTINGS = os.path.join(DATA, 'desktop_settings.json')
CLOUD_BASE = 'https://radar-cloud-production.up.railway.app'
UPDATE_MANIFEST = 'https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/updates/update_manifest.json'

BG = '#0f172a'
PANEL = '#1e293b'
PANEL2 = '#111827'
TEXT = '#f8fafc'
MUTED = '#94a3b8'
GREEN = '#16a34a'
RED = '#dc2626'
BLUE = '#2563eb'
BORDER = '#334155'
AMBER = '#f59e0b'
CYAN = '#22d3ee'

worker_proc = None
last_node_heartbeat = 0

def load_settings():
    try:
        return json.load(open(SETTINGS, 'r', encoding='utf-8')) if os.path.exists(SETTINGS) else {}
    except Exception:
        return {}

def save_settings(d):
    try:
        os.makedirs(DATA, exist_ok=True)
        with open(SETTINGS, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def ensure_node_id():
    d = load_settings()
    node_id = str(d.get('node_id') or '').strip()
    if not node_id:
        node_id = 'windows-' + uuid.uuid4().hex[:16]
        d['node_id'] = node_id
        save_settings(d)
    return node_id

def styled_dialog(title_text, message, kind='info', ask=False, secret=False):
    win = tk.Toplevel(root)
    win.title(title_text)
    win.configure(bg=BG)
    win.resizable(False, False)
    win.transient(root)
    win.grab_set()
    win.geometry('580x320')

    cardbox = tk.Frame(
        win, bg=PANEL, highlightthickness=1, highlightbackground=BORDER,
        padx=24, pady=22
    )
    cardbox.pack(fill='both', expand=True, padx=22, pady=22)
    accent = {'info': GREEN, 'ask': AMBER, 'error': RED}.get(kind, BLUE)
    tk.Label(
        cardbox, text=title_text, bg=PANEL, fg=accent,
        font=('Segoe UI', 16, 'bold')
    ).pack(anchor='w')
    tk.Label(
        cardbox, text=message, bg=PANEL, fg=TEXT, font=('Segoe UI', 10),
        justify='left', wraplength=490
    ).pack(anchor='w', pady=(14, 16))

    result = {'v': None}
    entry = None
    if secret:
        entry = tk.Entry(
            cardbox, show='•', bg=PANEL2, fg=TEXT, insertbackground=TEXT,
            relief='flat', font=('Segoe UI', 11)
        )
        entry.pack(fill='x', ipady=8, pady=(0, 14))
        entry.focus_set()

    row = tk.Frame(cardbox, bg=PANEL)
    row.pack(side='bottom', fill='x')

    def done(v):
        result['v'] = entry.get().strip() if secret and v else v
        win.destroy()

    if ask:
        tk.Button(
            row, text='CANCELAR', command=lambda: done(False),
            bg=PANEL2, fg=TEXT, relief='flat', bd=0, padx=18, pady=9
        ).pack(side='right', padx=(8, 0))
    tk.Button(
        row, text='ACEPTAR', command=lambda: done(True),
        bg=BLUE, fg='white', relief='flat', bd=0, padx=18, pady=9
    ).pack(side='right')
    win.protocol('WM_DELETE_WINDOW', lambda: done(False))
    root.wait_window(win)
    return result['v']

def refresh_windows_shortcuts():
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        return
    exe = os.path.join(APPDIR, 'InvestmentIntelligenceRadar.exe')
    try:
        ps = (
            "$ws=New-Object -ComObject WScript.Shell;"
            "$exe=$env:RADAR_EXE;"
            "$d=[Environment]::GetFolderPath('Desktop');"
            "$s=Join-Path $env:APPDATA 'Microsoft\\Windows\\Start Menu\\Programs';"
            "foreach($p in @((Join-Path $d 'Investment Intelligence Radar.lnk'),"
            "(Join-Path $s 'Investment Intelligence Radar.lnk'))){"
            "if(Test-Path $p){Remove-Item $p -Force};"
            "$x=$ws.CreateShortcut($p);$x.TargetPath=$exe;"
            "$x.WorkingDirectory=Split-Path $exe;$x.IconLocation=\"$exe,0\";$x.Save()}"
        )
        env = os.environ.copy()
        env['RADAR_EXE'] = exe
        subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps],
            env=env, creationflags=0x08000000,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15
        )
    except Exception:
        pass

def self_update_updater():
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        return

    def work():
        try:
            req = urllib.request.Request(
                UPDATE_MANIFEST,
                headers={'User-Agent': 'InvestmentIntelligenceRadarDesktop/1.3', 'Cache-Control': 'no-cache'}
            )
            m = json.loads(urllib.request.urlopen(req, timeout=12).read().decode('utf-8-sig'))
            url = m.get('updater_url')
            expected = (m.get('updater_sha256') or '').lower()
            if not url or not expected:
                return
            data = urllib.request.urlopen(
                urllib.request.Request(url, headers={'User-Agent': 'InvestmentIntelligenceRadarDesktop/1.3'}),
                timeout=45
            ).read()
            if hashlib.sha256(data).hexdigest().lower() != expected:
                return
            tmp = os.path.join(APPDIR, 'RadarUpdater.next.exe')
            with open(tmp, 'wb') as f:
                f.write(data)
            time.sleep(1)
            dst = os.path.join(APPDIR, 'RadarUpdater.exe')
            for _ in range(10):
                try:
                    os.replace(tmp, dst)
                    break
                except Exception:
                    time.sleep(1)
        except Exception:
            pass

    threading.Thread(target=work, daemon=True).start()

def pid_running(pid):
    if os.name == 'nt':
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def running():
    try:
        return os.path.exists(PID) and pid_running(int(open(PID).read().strip()))
    except Exception:
        return False

def start_worker():
    global worker_proc
    if running():
        return
    exe = os.path.join(APPDIR, 'RadarWorker.exe')
    flags = 0x08000000 if os.name == 'nt' else 0
    if os.path.exists(exe):
        worker_proc = subprocess.Popen([exe], cwd=APPDIR, creationflags=flags)
    else:
        worker_proc = subprocess.Popen(
            [sys.executable, os.path.join(os.path.dirname(__file__), 'run_worker.py')],
            cwd=os.path.dirname(__file__), creationflags=flags
        )

def stop_worker():
    try:
        pid = int(open(PID).read().strip())
        if os.name == 'nt':
            subprocess.run(
                ['taskkill', '/PID', str(pid), '/F'],
                creationflags=0x08000000,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            os.kill(pid, 15)
    except Exception:
        pass
    try:
        os.remove(PID)
    except Exception:
        pass

def cloud_get(path, timeout=7):
    req = urllib.request.Request(
        CLOUD_BASE + path,
        headers={'User-Agent': 'InvestmentIntelligenceRadarDesktop/1.3', 'Cache-Control': 'no-cache'}
    )
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8'))

def cloud_post(path, payload, timeout=8, prompt_token=False):
    settings = load_settings()
    token = str(settings.get('cloud_control_token') or '').strip()
    if not token and prompt_token:
        token = styled_dialog(
            'Conectar control Cloud',
            'Introduce la clave de control Cloud. Se guardará únicamente en este ordenador.',
            kind='ask', ask=True, secret=True
        )
        if not token:
            return None
        settings['cloud_control_token'] = token
        save_settings(settings)
    if not token:
        return None

    data = json.dumps(payload or {}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        CLOUD_BASE + path, data=data, method='POST',
        headers={
            'Authorization': 'Bearer ' + token,
            'User-Agent': 'InvestmentIntelligenceRadarDesktop/1.3',
            'Content-Type': 'application/json'
        }
    )
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            settings.pop('cloud_control_token', None)
            save_settings(settings)
        raise

def cloud_toggle():
    try:
        result = cloud_post('/toggle', {}, prompt_token=True)
        if result is not None:
            refresh_cloud()
    except urllib.error.HTTPError as e:
        styled_dialog('Cloud', f'Error HTTP {e.code}', 'error')
    except Exception as e:
        styled_dialog('Cloud', 'No se pudo contactar con Cloud:\n' + str(e), 'error')

def launch_updater():
    exe = os.path.join(APPDIR, 'RadarUpdater.exe')
    if not os.path.exists(exe):
        styled_dialog('Actualizaciones', 'El actualizador no está disponible.', 'error')
        return
    subprocess.Popen([exe], cwd=APPDIR, creationflags=0x08000000 if os.name == 'nt' else 0)
    root.after(600, root.destroy)

def card(parent, padx=16, pady=14):
    return tk.Frame(
        parent, bg=PANEL, highlightthickness=1,
        highlightbackground=BORDER, padx=padx, pady=pady
    )

def title(parent, text, size=12):
    return tk.Label(parent, text=text, bg=PANEL, fg=TEXT, font=('Segoe UI', size, 'bold'))

def small(parent, text='', var=None):
    return tk.Label(
        parent, text=text if var is None else None, textvariable=var,
        bg=PANEL, fg=MUTED, font=('Segoe UI', 9), justify='left'
    )

init_db()
refresh_windows_shortcuts()
self_update_updater()
ensure_node_id()

root = tk.Tk()
root.title('Investment Intelligence Radar')
root.geometry('1240x860')
root.minsize(980, 650)
root.configure(bg=BG)

canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
scroll = tk.Scrollbar(root, orient='vertical', command=canvas.yview)
canvas.configure(yscrollcommand=scroll.set)
scroll.pack(side='right', fill='y')
canvas.pack(side='left', fill='both', expand=True)

main = tk.Frame(canvas, bg=BG, padx=26, pady=22)
window_id = canvas.create_window((0, 0), window=main, anchor='nw')

def resize(e):
    canvas.itemconfigure(window_id, width=e.width)

canvas.bind('<Configure>', resize)
main.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
canvas.bind_all('<MouseWheel>', lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units'))

header = tk.Frame(main, bg=BG)
header.pack(fill='x')
hl = tk.Frame(header, bg=BG)
hl.pack(side='left', fill='x', expand=True)
tk.Label(
    hl, text='Investment Intelligence Radar',
    bg=BG, fg=TEXT, font=('Segoe UI', 24, 'bold')
).pack(anchor='w')
tk.Label(
    hl, text=f'Centro de inversión · Windows v{APP_VERSION} · trading real OFF',
    bg=BG, fg=MUTED, font=('Segoe UI', 10)
).pack(anchor='w', pady=(2, 12))
tk.Button(
    header, text='BUSCAR ACTUALIZACIÓN', command=launch_updater,
    font=('Segoe UI', 9, 'bold'), fg='white', bg=BLUE,
    relief='flat', bd=0, padx=16, pady=8, cursor='hand2'
).pack(side='right', anchor='n')

controls = tk.Frame(main, bg=BG)
controls.pack(fill='x', pady=(0, 10))

def compact_control(parent, name, desc):
    f = card(parent, 14, 10)
    left = tk.Frame(f, bg=PANEL)
    left.pack(side='left', fill='x', expand=True)
    tk.Label(left, text=name, bg=PANEL, fg=TEXT, font=('Segoe UI', 11, 'bold')).pack(anchor='w')
    state = tk.Label(left, text='COMPROBANDO', bg=PANEL, fg=AMBER, font=('Segoe UI', 9, 'bold'))
    state.pack(anchor='w')
    detail = tk.Label(
        left, text=desc, bg=PANEL, fg=MUTED, font=('Segoe UI', 8),
        wraplength=400, justify='left'
    )
    detail.pack(anchor='w')
    btn = tk.Button(
        f, text='ON', font=('Segoe UI', 9, 'bold'), fg='white',
        bg=GREEN, relief='flat', bd=0, padx=16, pady=7
    )
    btn.pack(side='right', padx=(12, 0))
    return f, state, detail, btn

pc_card, pc_state, pc_detail, pc_btn = compact_control(
    controls, 'Actividad PC', 'Recopilación y cálculo local.'
)
pc_card.pack(side='left', fill='x', expand=True, padx=(0, 5))
cloud_card, cloud_state, cloud_detail, cloud_btn = compact_control(
    controls, 'Actividad Cloud 24/7', 'Continúa aunque el PC esté apagado.'
)
cloud_card.pack(side='left', fill='x', expand=True, padx=(5, 0))

metrics = tk.Frame(main, bg=BG)
metrics.pack(fill='x', pady=(0, 10))
metric_vars = {k: tk.StringVar(value='—') for k in ['db', 'runs', 'prices', 'events', 'cloud', 'alerts']}
for i, (label, key) in enumerate([
    ('Base de datos', 'db'),
    ('Ciclos PC', 'runs'),
    ('Mercado PC', 'prices'),
    ('Eventos PC', 'events'),
    ('Cloud', 'cloud'),
    ('Alertas', 'alerts'),
]):
    f = tk.Frame(
        metrics, bg=PANEL2, highlightthickness=1,
        highlightbackground=BORDER, padx=10, pady=8
    )
    f.grid(row=0, column=i, sticky='nsew', padx=3)
    metrics.grid_columnconfigure(i, weight=1)
    tk.Label(f, text=label, bg=PANEL2, fg=MUTED, font=('Segoe UI', 8)).pack(anchor='w')
    tk.Label(
        f, textvariable=metric_vars[key], bg=PANEL2, fg=TEXT,
        font=('Segoe UI', 12, 'bold')
    ).pack(anchor='w')

cloud_counts = tk.StringVar(value='Mercado — · Eventos — · Ciclos —')
cf = card(main, 14, 9)
cf.pack(fill='x', pady=(0, 10))
title(cf, 'Actividad Cloud verificada', 10).pack(side='left')
small(cf, var=cloud_counts).pack(side='right')

intel = card(main)
intel.pack(fill='x', pady=(0, 10))
title(intel, 'Inteligencia · señales, fuentes y alertas', 13).pack(anchor='w')
tk.Label(
    intel,
    text='Detector de silencio: movimientos estadísticamente anómalos sin catalizador público detectado. '
         'La reputación de fuentes se recalcula con observaciones acumuladas.',
    bg=PANEL, fg=MUTED, font=('Segoe UI', 9), justify='left', wraplength=1100
).pack(anchor='w', pady=(3, 9))
intelrow = tk.Frame(intel, bg=PANEL)
intelrow.pack(fill='x')
intel_lists = {}
for i, (label, key) in enumerate([
    ('Alertas de silencio', 'silence'),
    ('Reputación de fuentes', 'sources'),
    ('Notificaciones', 'notifications'),
]):
    box = tk.Frame(intelrow, bg=PANEL2, padx=8, pady=8)
    box.grid(row=0, column=i, sticky='nsew', padx=4)
    intelrow.grid_columnconfigure(i, weight=1)
    tk.Label(box, text=label, bg=PANEL2, fg=TEXT, font=('Segoe UI', 9, 'bold')).pack(anchor='w')
    lb = tk.Listbox(
        box, height=6, bg=PANEL2, fg=TEXT,
        highlightthickness=0, bd=0, font=('Segoe UI', 8)
    )
    lb.pack(fill='both', expand=True, pady=(6, 0))
    intel_lists[key] = lb

sim = card(main)
sim.pack(fill='x', pady=(0, 10))
title(sim, 'Simulador autónomo · capital ficticio', 13).pack(anchor='w')
tk.Label(
    sim,
    text='Objetivo: hacer crecer el capital con riesgo limitado. '
         'Sin apalancamiento, sin posiciones cortas y con límites de concentración.',
    bg=PANEL, fg=MUTED, font=('Segoe UI', 9)
).pack(anchor='w', pady=(3, 10))

sim_top = tk.Frame(sim, bg=PANEL)
sim_top.pack(fill='x')
amount = tk.StringVar(value='1000')
tk.Label(sim_top, text='Capital inicial (€)', bg=PANEL, fg=MUTED, font=('Segoe UI', 9)).pack(side='left')
tk.Entry(
    sim_top, textvariable=amount, width=10, bg=PANEL2, fg=TEXT,
    insertbackground=TEXT, relief='flat', font=('Segoe UI', 10)
).pack(side='left', padx=8, ipady=5)
sim_status = tk.StringVar(value='Sin iniciar')
tk.Label(
    sim_top, textvariable=sim_status, bg=PANEL, fg=CYAN,
    font=('Segoe UI', 10, 'bold')
).pack(side='left', padx=12)

def start_sim():
    sim_status.set('Preparando histórico y cartera…')
    def work():
        try:
            paper_start(float(amount.get().replace(',', '.')))
            root.after(0, lambda: sim_status.set('Simulación activa'))
        except Exception as e:
            root.after(0, lambda: styled_dialog('Simulador', 'No se pudo iniciar:\n' + str(e), 'error'))
    threading.Thread(target=work, daemon=True).start()

def step_sim():
    def work():
        try:
            paper_step(force=True)
            root.after(0, refresh_investment)
        except Exception as e:
            root.after(0, lambda: styled_dialog('Simulador', 'No se pudo ejecutar decisión:\n' + str(e), 'error'))
    threading.Thread(target=work, daemon=True).start()

tk.Button(
    sim_top, text='INICIAR / REINICIAR', command=start_sim,
    bg=BLUE, fg='white', relief='flat', bd=0, padx=14, pady=7
).pack(side='right')
tk.Button(
    sim_top, text='DECIDIR AHORA', command=step_sim,
    bg=PANEL2, fg=TEXT, relief='flat', bd=0, padx=14, pady=7
).pack(side='right', padx=8)

sim_summary = tk.StringVar(value='Capital — · Efectivo — · Invertido — · P/L —')
tk.Label(
    sim, textvariable=sim_summary, bg=PANEL, fg=TEXT,
    font=('Segoe UI', 12, 'bold')
).pack(anchor='w', pady=(12, 7))
positions = tk.Listbox(
    sim, height=5, bg=PANEL2, fg=TEXT,
    highlightthickness=0, bd=0, font=('Consolas', 9)
)
positions.pack(fill='x')

rankrow = tk.Frame(main, bg=BG)
rankrow.pack(fill='x', pady=(0, 10))
hist_card = card(rankrow)
hist_card.pack(side='left', fill='both', expand=True, padx=(0, 5))
opp_card = card(rankrow)
opp_card.pack(side='left', fill='both', expand=True, padx=(5, 0))
title(hist_card, 'Más rentables según histórico', 12).pack(anchor='w')
title(opp_card, 'Mejores inversiones potenciales', 12).pack(anchor='w')
hist_text = tk.Text(
    hist_card, height=12, bg=PANEL2, fg=TEXT,
    highlightthickness=0, bd=0, font=('Consolas', 9)
)
hist_text.pack(fill='both', expand=True, pady=(8, 0))
opp_text = tk.Text(
    opp_card, height=12, bg=PANEL2, fg=TEXT,
    highlightthickness=0, bd=0, font=('Consolas', 9)
)
opp_text.pack(fill='both', expand=True, pady=(8, 0))

body = tk.Frame(main, bg=BG)
body.pack(fill='x', pady=(0, 10))
left = card(body)
left.pack(side='left', fill='both', expand=True, padx=(0, 5))
right = card(body)
right.pack(side='left', fill='both', expand=True, padx=(5, 0))
title(left, 'Últimos precios · PC local', 11).pack(anchor='w')
title(right, 'Últimos eventos · PC local', 11).pack(anchor='w')
prices = tk.Listbox(
    left, height=9, bg=PANEL2, fg=TEXT,
    highlightthickness=0, bd=0, font=('Consolas', 9)
)
prices.pack(fill='both', expand=True, pady=(7, 0))
events = tk.Listbox(
    right, height=9, bg=PANEL2, fg=TEXT,
    highlightthickness=0, bd=0, font=('Segoe UI', 8)
)
events.pack(fill='both', expand=True, pady=(7, 0))
tk.Label(
    main, text='Trading real: OFF · El simulador utiliza únicamente dinero ficticio.',
    bg=BG, fg=MUTED, font=('Segoe UI', 9)
).pack(anchor='w', pady=(2, 12))

def toggle_pc():
    if running():
        stop_worker()
    else:
        start_worker()
    root.after(700, refresh_local)

def refresh_local():
    r = running()
    pc_btn.configure(text='OFF' if r else 'ON', bg=RED if r else GREEN)
    pc_state.configure(text='ACTIVO' if r else 'DETENIDO', fg='#4ade80' if r else '#f87171')
    try:
        p, e, rr, latest, news = stats()
        metric_vars['db'].set('CONECTADA')
        metric_vars['prices'].set(str(p))
        metric_vars['events'].set(str(e))
        metric_vars['runs'].set(str(rr))
        st = {}
        try:
            st = json.load(open(STATUS, 'r', encoding='utf-8')) if os.path.exists(STATUS) else {}
        except Exception:
            pass
        pc_detail.configure(
            text=(st.get('last_detail') or ('Motor local activo.' if r else 'Motor local detenido.'))[:160]
        )
        prices.delete(0, 'end')
        for s, p_, src, ts in latest:
            prices.insert('end', f'{s:<7} {p_:>11.3f}  {src}')
        events.delete(0, 'end')
        for src, t, ts in news:
            events.insert('end', f'[{src}] {t}')
    except Exception as ex:
        metric_vars['db'].set('ERROR')
        pc_detail.configure(text='Error: ' + str(ex)[:140])
    root.after(3000, refresh_local)

def refresh_intelligence(snap):
    intel_data = snap.get('intelligence') or {}
    silence = intel_data.get('silence_alerts') or []
    sources = intel_data.get('source_reputation') or []
    notifs = intel_data.get('notifications') or []
    metric_vars['alerts'].set(str(len(silence)))

    lb = intel_lists['silence']
    lb.delete(0, 'end')
    if not silence:
        lb.insert('end', 'Sin alertas abiertas')
    for a in silence[:12]:
        lb.insert('end', f"{a.get('symbol','?')} · z {a.get('z_score',0):+.2f} · {a.get('return_pct',0):+.2f}%")

    lb = intel_lists['sources']
    lb.delete(0, 'end')
    if not sources:
        lb.insert('end', 'Aún sin reputación calculada')
    for s in sources[:12]:
        lb.insert('end', f"{s.get('source','?')} · {s.get('score',0):.1f}/100 · conf {s.get('confidence',0)*100:.0f}%")

    lb = intel_lists['notifications']
    lb.delete(0, 'end')
    if not notifs:
        lb.insert('end', 'Sin notificaciones')
    for n in notifs[:12]:
        mark = '• ' if not n.get('read') else ''
        lb.insert('end', f"{mark}{n.get('severity','')} · {n.get('title','')}")

def maybe_node_heartbeat():
    global last_node_heartbeat
    if time.time() - last_node_heartbeat < 60:
        return
    settings = load_settings()
    if not str(settings.get('cloud_control_token') or '').strip():
        return
    last_node_heartbeat = time.time()
    try:
        cloud_post('/node-heartbeat', {
            'node_id': ensure_node_id(),
            'node_type': 'desktop',
            'name': os.environ.get('COMPUTERNAME', 'Windows PC'),
            'capabilities': ['local-collector', 'paper-simulator', 'desktop-ui'],
            'app_version': APP_VERSION,
            'detail': 'Nodo Windows activo',
        })
    except Exception:
        pass

def refresh_cloud():
    try:
        d = cloud_get('/health')
        enabled = bool(d.get('cloud_enabled', True))
        snap = cloud_get('/snapshot')
        c = snap.get('counts', {})
        st = snap.get('status', {})
        cloud_state.configure(
            text='ACTIVO 24/7' if enabled else 'PAUSADO',
            fg='#4ade80' if enabled else '#f87171'
        )
        cloud_btn.configure(text='OFF' if enabled else 'ON', bg=RED if enabled else GREEN)
        metric_vars['cloud'].set('ONLINE' if enabled else 'PAUSADO')
        cloud_counts.set(
            f"Mercado {c.get('prices', 0)} · Eventos {c.get('events', 0)} · Ciclos {c.get('runs', 0)}"
        )
        detail = st.get('last_detail') or st.get('state') or 'Servicio disponible'
        cloud_detail.configure(text=('Cloud activo · ' + str(detail))[:180])
        refresh_intelligence(snap)
        maybe_node_heartbeat()
    except Exception as e:
        cloud_state.configure(text='SIN CONEXIÓN', fg='#f87171')
        metric_vars['cloud'].set('OFFLINE')
        cloud_detail.configure(text=str(e)[:160])
    root.after(5000, refresh_cloud)

def refresh_investment():
    try:
        st = paper_status()
        sim_status.set(
            'ACTIVA' if st.get('enabled')
            else ('PAUSADA' if st.get('configured') else 'Sin iniciar')
        )
        sim_summary.set(
            f"Capital {st.get('total', 0):.2f} € · "
            f"Efectivo {st.get('cash', 0):.2f} € · "
            f"Invertido {st.get('invested', 0):.2f} € · "
            f"P/L {st.get('pnl', 0):+.2f} € ({st.get('pnl_pct', 0):+.2f}%)"
        )
        positions.delete(0, 'end')
        for p in st.get('positions', []):
            positions.insert(
                'end',
                f"{p.get('symbol','?'):<7} {p.get('value',0):>9.2f} €   {p.get('pnl_pct',0):+6.2f}%"
            )

        hist_text.delete('1.0', 'end')
        for label, days in [('SEMANA', 7), ('MES', 30), ('AÑO', 365)]:
            hist_text.insert('end', label + '\n')
            leaders = profitability_leaders(days, 5)
            if not leaders:
                hist_text.insert('end', '  Sin histórico suficiente\n')
            else:
                for x in leaders:
                    hist_text.insert('end', f"  {x['symbol']:<7} {x['return_pct']:+7.2f}%\n")
            hist_text.insert('end', '\n')

        opp_text.delete('1.0', 'end')
        ranks = opportunity_rankings(4)
        for tier in ('bajo', 'intermedio', 'alto'):
            opp_text.insert('end', tier.upper() + '\n')
            vals = ranks.get(tier, [])
            if not vals:
                opp_text.insert('end', '  Sin datos suficientes\n')
            else:
                for x in vals:
                    opp_text.insert(
                        'end',
                        f"  {x['symbol']:<7} score {x['score']:6.2f} · vol {x['volatility']:5.1f}%\n"
                    )
            opp_text.insert('end', '\n')
    except Exception as e:
        sim_status.set('Error: ' + str(e)[:80])
    root.after(10000, refresh_investment)

def ensure_history_bg():
    if history_ready():
        return
    def work():
        try:
            collect_history()
            root.after(0, refresh_investment)
        except Exception:
            pass
    threading.Thread(target=work, daemon=True).start()

pc_btn.configure(command=toggle_pc)
cloud_btn.configure(command=cloud_toggle)

start_worker()
ensure_history_bg()
refresh_local()
refresh_cloud()
refresh_investment()
root.mainloop()
