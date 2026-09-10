"""Cloud-aware Simulation Lab adapter.

The autonomous simulator authority runs continuously in Cloud. This desktop view
observes that canonical runtime directly instead of showing only the local SQLite
simulation tables. It never starts a second autonomous writer process and never
enables real trading.
"""
import json
import threading
import urllib.request

import radar_simulation_desktop as base

REAL_TRADING=False
CLOUD_BASE='https://radar-cloud-production.up.railway.app'
_CLOUD_ENDPOINTS={
    'simulator':'/simulator-status-v1',
    'equity':'/simulator-equity-v1',
    'e2e':'/autonomy-e2e-v1',
    'soak':'/autonomy-soak-v1',
}


def _cloud_get(path,timeout=8):
    req=urllib.request.Request(CLOUD_BASE+path,headers={'User-Agent':'RadarSimulationLab/'+str(base.APP_VERSION),'Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def format_autonomy_status(simulator,e2e=None,soak=None,error=None):
    simulator=simulator or {};e2e=e2e or {};soak=soak or {}
    if not simulator:
        return 'Cloud sin datos todavía'+((' · '+str(error)[:140]) if error else '')
    paper=simulator.get('paper') or {}
    state=simulator.get('status') or ('ACTIVE' if simulator.get('active') else 'PAUSED')
    return (
        f"Cloud {state} · generación {simulator.get('generation','—')} · "
        f"ciclos {simulator.get('completed_cycles',0)} · experimentos {simulator.get('completed_experiments',0)} · "
        f"PAPER {'ON' if paper.get('enabled') else 'OFF'} · capital {base.fmt(paper.get('total'),2,' €')} · "
        f"soak {soak.get('status','—')} · E2E {e2e.get('status','—')} · REAL TRADING OFF"
    )


def format_recent_runs(simulator,limit=8):
    out=[]
    for row in list((simulator or {}).get('recent_runs') or [])[:limit]:
        out.append(
            f"CLOUD  {str(row.get('completed_at') or row.get('started_at') or '—')[:19]}  "
            f"run {row.get('run_id','—')}  gen {row.get('generation','—')}  "
            f"{row.get('status','—')}  paper={row.get('paper_status','—')}  research={row.get('research_status','—')}"
        )
    return out


def format_recent_experiments(simulator,limit=6):
    out=[]
    for row in list((simulator or {}).get('recent_experiments') or [])[:limit]:
        out.append(
            f"{row.get('experiment_id','—')} · gen {row.get('generation','—')} · "
            f"{row.get('stage','—')} · gate {row.get('gate_status','—')} · score {base.fmt(row.get('research_score'),3)}"
        )
    return out


def equity_chart_points(series,width,height,left=16,right=16,top=28,bottom=25):
    """Return deterministic plot coordinates for observed daily equity values."""
    clean=[]
    for raw in series or []:
        if not isinstance(raw,dict):continue
        try:value=float(raw.get('equity'))
        except (TypeError,ValueError):continue
        clean.append((str(raw.get('date') or raw.get('day') or '')[:10],value))
    if not clean:return []
    w=max(1.0,float(width)-left-right);h=max(1.0,float(height)-top-bottom)
    values=[v for _,v in clean];lo=min(values);hi=max(values)
    if hi<=lo:
        pad=max(abs(lo)*0.005,1.0);lo-=pad;hi+=pad
    points=[];n=len(clean)
    for i,(day,value) in enumerate(clean):
        x=left+(w/2.0 if n==1 else w*i/(n-1))
        y=top+(hi-value)/(hi-lo)*h
        points.append({'x':x,'y':y,'date':day,'equity':value})
    return points


def equity_summary_text(equity):
    equity=equity or {};observed=int(equity.get('observed_days') or 0);window=int(equity.get('window_days') or 30)
    return f"{observed} días observados · ventana {window}d · sin backfill"


class CloudAwareLab(base.Lab):
    def __init__(self,root):
        self.cloud_simulator={};self.cloud_equity={};self.cloud_e2e={};self.cloud_soak={};self.cloud_error='';self.cloud_loading=False
        super().__init__(root)
        self._pull_cloud_async()

    def build(self):
        super().build()
        c=base.card(self.main);c.pack(fill='x',pady=(0,10))
        base.lbl(c,'Simulador autónomo 24/7 · Cloud',size=13,bold=True).pack(anchor='w')
        self.autonomy_txt=base.tk.StringVar(value='Conectando con el simulador autónomo…')
        self.autonomy_detail=base.tk.StringVar(value='')
        base.tk.Label(c,textvariable=self.autonomy_txt,bg=base.PANEL,fg=base.GREEN,font=('Segoe UI',10,'bold'),wraplength=1160,justify='left').pack(anchor='w',pady=(6,2))
        base.tk.Label(c,textvariable=self.autonomy_detail,bg=base.PANEL,fg=base.MUTED,font=('Segoe UI',9),wraplength=1160,justify='left').pack(anchor='w')

        graph_row=base.tk.Frame(c,bg=base.PANEL);graph_row.pack(fill='x',pady=(10,2))
        self.equity_canvas=base.tk.Canvas(graph_row,height=175,bg=base.PANEL2,highlightthickness=1,highlightbackground=base.BORDER,bd=0)
        self.equity_canvas.pack(side='left',fill='both',expand=True,padx=(0,12))
        self.equity_canvas.bind('<Configure>',lambda _event:self._draw_equity_chart())
        stats=base.tk.Frame(graph_row,bg=base.PANEL,width=220);stats.pack(side='right',fill='y');stats.pack_propagate(False)
        base.lbl(stats,'EQUITY PAPER · 30 DÍAS',base.MUTED,8,True).pack(anchor='w',pady=(4,2))
        self.equity_value=base.tk.StringVar(value='—');self.equity_change=base.tk.StringVar(value='—');self.equity_range=base.tk.StringVar(value='—');self.equity_history=base.tk.StringVar(value='Esperando histórico…')
        base.tk.Label(stats,textvariable=self.equity_value,bg=base.PANEL,fg=base.TEXT,font=('Segoe UI',18,'bold')).pack(anchor='w')
        self.equity_change_label=base.tk.Label(stats,textvariable=self.equity_change,bg=base.PANEL,fg=base.CYAN,font=('Segoe UI',11,'bold'));self.equity_change_label.pack(anchor='w',pady=(2,6))
        base.tk.Label(stats,textvariable=self.equity_range,bg=base.PANEL,fg=base.TEXT,font=('Segoe UI',9),justify='left').pack(anchor='w')
        base.tk.Label(stats,textvariable=self.equity_history,bg=base.PANEL,fg=base.MUTED,font=('Segoe UI',8),wraplength=210,justify='left').pack(anchor='w',pady=(7,0))

    def _pull_cloud_async(self):
        if self.cloud_loading:return
        self.cloud_loading=True
        def work():
            payloads={};errors=[]
            for key,path in _CLOUD_ENDPOINTS.items():
                try:payloads[key]=_cloud_get(path)
                except Exception as exc:errors.append(key+': '+str(exc)[:120])
            def apply():
                self.cloud_loading=False
                if payloads.get('simulator'):self.cloud_simulator=payloads['simulator']
                if payloads.get('equity'):self.cloud_equity=payloads['equity']
                if payloads.get('e2e'):self.cloud_e2e=payloads['e2e']
                if payloads.get('soak'):self.cloud_soak=payloads['soak']
                self.cloud_error=' | '.join(errors)
                self._render_cloud()
            try:self.root.after(0,apply)
            except Exception:self.cloud_loading=False
        threading.Thread(target=work,name='simulation-lab-cloud-status',daemon=True).start()

    def _draw_equity_chart(self):
        canvas=getattr(self,'equity_canvas',None)
        if canvas is None:return
        canvas.delete('all');width=max(canvas.winfo_width(),520);height=max(canvas.winfo_height(),175)
        canvas.create_text(16,10,anchor='nw',text='EVOLUCIÓN PAPER · ÚLTIMOS 30 DÍAS',fill=base.MUTED,font=('Segoe UI',8,'bold'))
        series=list((self.cloud_equity or {}).get('daily_equity_30d') or [])
        points=equity_chart_points(series,width,height)
        if not points:
            canvas.create_text(width/2,height/2,anchor='center',text='Acumulando histórico diario real…',fill=base.MUTED,font=('Segoe UI',10))
            return
        start_y=points[0]['y'];canvas.create_line(16,start_y,width-16,start_y,fill=base.BORDER,dash=(3,5),width=1)
        if len(points)==1:
            p=points[0];canvas.create_oval(p['x']-5,p['y']-5,p['x']+5,p['y']+5,outline=base.CYAN,fill=base.GREEN,width=2)
        else:
            for previous,current in zip(points,points[1:]):
                rising=current['equity']>=previous['equity'];color=base.GREEN if rising else base.RED
                canvas.create_line(previous['x'],previous['y'],current['x'],current['y'],fill=base.BORDER,width=5)
                canvas.create_line(previous['x'],previous['y'],current['x'],current['y'],fill=color,width=3)
            last=points[-1];canvas.create_oval(last['x']-5,last['y']-5,last['x']+5,last['y']+5,outline=base.CYAN,fill=base.GREEN if last['equity']>=points[-2]['equity'] else base.RED,width=2)
        canvas.create_text(16,height-8,anchor='sw',text=points[0]['date'][5:],fill=base.MUTED,font=('Segoe UI',8))
        canvas.create_text(width-16,height-8,anchor='se',text=points[-1]['date'][5:],fill=base.MUTED,font=('Segoe UI',8))

    def _render_equity_summary(self):
        eq=self.cloud_equity or {};current=eq.get('current_equity');change=eq.get('month_change_pct');high=eq.get('month_high');low=eq.get('month_low')
        self.equity_value.set(base.fmt(current,2,' €'))
        if change is None:
            self.equity_change.set('Variación: —');self.equity_change_label.configure(fg=base.CYAN)
        else:
            value=float(change);self.equity_change.set(f"30d observado: {value:+.2f}%");self.equity_change_label.configure(fg=base.GREEN if value>=0 else base.RED)
        self.equity_range.set(f"Máx  {base.fmt(high,2,' €')}\nMín  {base.fmt(low,2,' €')}")
        self.equity_history.set(equity_summary_text(eq))
        self._draw_equity_chart()

    def _render_cloud(self):
        sim=self.cloud_simulator or {}
        self.autonomy_txt.set(format_autonomy_status(sim,self.cloud_e2e,self.cloud_soak,self.cloud_error))
        experiments=format_recent_experiments(sim)
        last_cycle=sim.get('last_cycle_at') or '—';last_research=sim.get('last_research_at') or '—';err=sim.get('last_error') or self.cloud_error or 'ninguno'
        self.autonomy_detail.set(
            f"Último ciclo {str(last_cycle)[:19]} · última investigación {str(last_research)[:19]} · "
            f"cola {sim.get('queued_experiments',0)} · error {str(err)[:120]}"+
            (("\nExperimentos recientes: "+' | '.join(experiments)) if experiments else '')
        )
        if hasattr(self,'equity_value'):self._render_equity_summary()
        cloud_runs=format_recent_runs(sim)
        if cloud_runs:
            self.runs.delete(0,'end')
            for line in cloud_runs:self.runs.insert('end',line)

    def refresh(self):
        super().refresh()
        if hasattr(self,'autonomy_txt'):self._render_cloud()

    def tick(self):
        if not self.busy:self.refresh()
        self._pull_cloud_async()
        self.root.after(5000,self.tick)


def main():
    base.ensure_agents();base.champion_status();root=base.tk.Tk();CloudAwareLab(root);root.mainloop()


if __name__=='__main__':main()
