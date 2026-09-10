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


class CloudAwareLab(base.Lab):
    def __init__(self,root):
        self.cloud_simulator={};self.cloud_e2e={};self.cloud_soak={};self.cloud_error='';self.cloud_loading=False
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

    def _pull_cloud_async(self):
        if self.cloud_loading:return
        self.cloud_loading=True
        def work():
            error='';sim={};e2e={};soak={}
            try:
                sim=_cloud_get(_CLOUD_ENDPOINTS['simulator'])
                e2e=_cloud_get(_CLOUD_ENDPOINTS['e2e'])
                soak=_cloud_get(_CLOUD_ENDPOINTS['soak'])
            except Exception as exc:error=str(exc)[:300]
            def apply():
                self.cloud_loading=False
                if sim:self.cloud_simulator=sim
                if e2e:self.cloud_e2e=e2e
                if soak:self.cloud_soak=soak
                self.cloud_error=error
                self._render_cloud()
            try:self.root.after(0,apply)
            except Exception:self.cloud_loading=False
        threading.Thread(target=work,name='simulation-lab-cloud-status',daemon=True).start()

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
