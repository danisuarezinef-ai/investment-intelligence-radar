import csv,json,os,threading
import tkinter as tk
from tkinter import ttk

from radar_core import DATA,con
from radar_agents import ensure_agents,agents_status,reset_agents
from radar_simulation_v2 import replay_historical
from radar_simulation_forward_v3 import simulation_summary_v3
from radar_decision_memory_v2 import memory_health,calibration_profile
from radar_learning_v2 import learning_v2_health
from radar_meta_decision_v2 import champion_decision
from radar_champion_portfolio import champion_status,reset_champion
from radar_runtime_v2 import safe_fast_cycle,safe_deep_cycle

REAL_TRADING=False
APP_VERSION='1.5.1'
BG='#0f172a';PANEL='#1e293b';PANEL2='#111827';TEXT='#f8fafc';MUTED='#94a3b8';GREEN='#16a34a';RED='#dc2626';BLUE='#2563eb';BORDER='#334155';CYAN='#22d3ee';AMBER='#f59e0b'

def fmt(v,d=2,s=''):
    try:return f'{float(v):.{d}f}{s}'
    except Exception:return '—'
def card(p):return tk.Frame(p,bg=PANEL,highlightthickness=1,highlightbackground=BORDER,padx=14,pady=12)
def lbl(p,t='',fg=TEXT,size=9,bold=False):return tk.Label(p,text=t,bg=p.cget('bg'),fg=fg,font=('Segoe UI',size,'bold' if bold else 'normal'),justify='left')
def safe(x,default='—'):return default if x is None else x

class Lab:
    def __init__(self,root):
        self.root=root;self.busy=False;self.last_export=None
        root.title('Investment Intelligence Radar · Simulation Lab');root.geometry('1320x930');root.minsize(1040,720);root.configure(bg=BG)
        cv=tk.Canvas(root,bg=BG,highlightthickness=0);sb=tk.Scrollbar(root,orient='vertical',command=cv.yview);cv.configure(yscrollcommand=sb.set);sb.pack(side='right',fill='y');cv.pack(side='left',fill='both',expand=True)
        self.main=tk.Frame(cv,bg=BG,padx=24,pady=20);wid=cv.create_window((0,0),window=self.main,anchor='nw');cv.bind('<Configure>',lambda e:cv.itemconfigure(wid,width=e.width));self.main.bind('<Configure>',lambda e:cv.configure(scrollregion=cv.bbox('all')))
        cv.bind_all('<MouseWheel>',lambda e:cv.yview_scroll(int(-1*(e.delta/120)),'units'))
        self.build();ensure_agents();champion_status();self.refresh();root.after(5000,self.tick)

    def build(self):
        head=tk.Frame(self.main,bg=BG);head.pack(fill='x')
        hleft=tk.Frame(head,bg=BG);hleft.pack(side='left',fill='x',expand=True)
        lbl(hleft,'Simulation Lab',size=24,bold=True).pack(anchor='w');lbl(hleft,f'5 agentes + Champion calibrado · Windows v{APP_VERSION} · TRADING REAL OFF',MUTED,10).pack(anchor='w',pady=(0,12))
        tk.Button(head,text='EXPORTAR INFORME',command=self.export,bg=PANEL2,fg=TEXT,relief='flat',bd=0,padx=14,pady=8).pack(side='right',anchor='n')

        c=card(self.main);c.pack(fill='x',pady=(0,10));lbl(c,'Control de simulación',size=12,bold=True).pack(side='left');self.status=tk.StringVar(value='Listo');tk.Label(c,textvariable=self.status,bg=PANEL,fg=CYAN,font=('Segoe UI',9,'bold')).pack(side='left',padx=14)
        for text,cmd,bg in [('DECIDIR AHORA',self.fast,BLUE),('APRENDIZAJE PROFUNDO',self.deep,PANEL2),('REINICIAR TODO 200 €',self.reset,PANEL2)]:tk.Button(c,text=text,command=cmd,bg=bg,fg='white',relief='flat',bd=0,padx=12,pady=7).pack(side='right',padx=4)

        ch=card(self.main);ch.pack(fill='x',pady=(0,10));lbl(ch,'Champion adaptativo · decisión automática',size=13,bold=True).pack(anchor='w')
        self.champion=tk.StringVar(value='—');self.chdetail=tk.StringVar(value='—');self.chportfolio=tk.StringVar(value='—');self.calibration=tk.StringVar(value='—')
        tk.Label(ch,textvariable=self.champion,bg=PANEL,fg=GREEN,font=('Segoe UI',16,'bold')).pack(anchor='w',pady=(6,2));tk.Label(ch,textvariable=self.chportfolio,bg=PANEL,fg=TEXT,font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(0,2));tk.Label(ch,textvariable=self.calibration,bg=PANEL,fg=AMBER,font=('Segoe UI',9,'bold'),wraplength=1160,justify='left').pack(anchor='w',pady=(1,2));tk.Label(ch,textvariable=self.chdetail,bg=PANEL,fg=MUTED,font=('Segoe UI',9),wraplength=1160,justify='left').pack(anchor='w')

        a=card(self.main);a.pack(fill='x',pady=(0,10));lbl(a,'Agentes simulados + Champion',size=13,bold=True).pack(anchor='w');cols=('agente','total','pnl','invertido','drawdown','sharpe','sortino','alpha','trades','costes');self.tree=ttk.Treeview(a,columns=cols,show='headings',height=7)
        spec=[('agente','Agente',160),('total','Capital',100),('pnl','P/L',90),('invertido','Invertido',100),('drawdown','Max DD',90),('sharpe','Sharpe',80),('sortino','Sortino',80),('alpha','Alpha',80),('trades','Ops',60),('costes','Costes',80)]
        for col,h,w in spec:self.tree.heading(col,text=h);self.tree.column(col,width=w,anchor='w' if col=='agente' else 'center')
        self.tree.pack(fill='x',pady=(8,0))

        s=card(self.main);s.pack(fill='x',pady=(0,10));lbl(s,'Forward Simulation v3 · auditoría',size=12,bold=True).pack(anchor='w');self.simtxt=tk.StringVar(value='—');self.audit=tk.StringVar(value='—');tk.Label(s,textvariable=self.simtxt,bg=PANEL,fg=TEXT,font=('Segoe UI',10),wraplength=1160,justify='left').pack(anchor='w',pady=(5,1));tk.Label(s,textvariable=self.audit,bg=PANEL,fg=CYAN,font=('Segoe UI',9),wraplength=1160,justify='left').pack(anchor='w')

        row=tk.Frame(self.main,bg=BG);row.pack(fill='x',pady=(0,10));m=card(row);m.pack(side='left',fill='both',expand=True,padx=(0,5));l=card(row);l.pack(side='left',fill='both',expand=True,padx=(5,0));lbl(m,'Memoria episódica',size=12,bold=True).pack(anchor='w');lbl(l,'Aprendizaje y habilidades',size=12,bold=True).pack(anchor='w');self.memtxt=tk.StringVar(value='—');self.learntxt=tk.StringVar(value='—');tk.Label(m,textvariable=self.memtxt,bg=PANEL,fg=TEXT,font=('Segoe UI',9),wraplength=545,justify='left').pack(anchor='w',pady=(6,0));tk.Label(l,textvariable=self.learntxt,bg=PANEL,fg=TEXT,font=('Segoe UI',9),wraplength=545,justify='left').pack(anchor='w',pady=(6,0))

        ev=card(self.main);ev.pack(fill='x',pady=(0,10));lbl(ev,'Evidencia forward y horizontes shadow',size=12,bold=True).pack(anchor='w');self.evidence=tk.StringVar(value='—');tk.Label(ev,textvariable=self.evidence,bg=PANEL,fg=TEXT,font=('Segoe UI',9),wraplength=1160,justify='left').pack(anchor='w',pady=(5,0))

        r=card(self.main);r.pack(fill='x',pady=(0,10));lbl(r,'Replay histórico point-in-time',size=12,bold=True).pack(anchor='w');rr=tk.Frame(r,bg=PANEL);rr.pack(fill='x',pady=(7,5));self.start=tk.StringVar();self.end=tk.StringVar();self.cash=tk.StringVar(value='200')
        for t,v,w in [('Inicio YYYY-MM-DD',self.start,15),('Fin YYYY-MM-DD',self.end,15),('Capital/agente',self.cash,10)]:lbl(rr,t,MUTED,8).pack(side='left',padx=(0,4));tk.Entry(rr,textvariable=v,width=w,bg=PANEL2,fg=TEXT,insertbackground=TEXT,relief='flat').pack(side='left',padx=(0,10),ipady=5)
        tk.Button(rr,text='EJECUTAR REPLAY',command=self.replay,bg=BLUE,fg='white',relief='flat',bd=0,padx=14,pady=7).pack(side='right');self.replaytxt=tk.StringVar(value='Sin look-ahead: cada decisión usa sólo información disponible hasta esa fecha.');tk.Label(r,textvariable=self.replaytxt,bg=PANEL,fg=MUTED,font=('Segoe UI',9),wraplength=1160,justify='left').pack(anchor='w')

        runs=card(self.main);runs.pack(fill='x',pady=(0,10));lbl(runs,'Últimas simulaciones',size=12,bold=True).pack(anchor='w');self.runs=tk.Listbox(runs,height=5,bg=PANEL2,fg=TEXT,highlightthickness=0,bd=0,font=('Consolas',9));self.runs.pack(fill='x',pady=(7,0))
        lbl(self.main,'Los resultados simulados no implican rendimiento futuro. Trading real permanece desactivado.',MUTED,9).pack(anchor='w')

    def run(self,name,fn):
        if self.busy:return
        self.busy=True;self.status.set(name+'…')
        def work():
            try:res=fn();self.root.after(0,lambda:self.done(name,res,None))
            except Exception as e:self.root.after(0,lambda:self.done(name,None,e))
        threading.Thread(target=work,daemon=True).start()
    def done(self,name,res,err):
        self.busy=False;self.status.set(('ERROR · '+str(err)[:100]) if err else name+' completado')
        if not err and name=='Replay histórico' and isinstance(res,dict):
            lead=res.get('leader') or {};self.replaytxt.set(f"Completado · {res.get('start_date','—')} → {res.get('end_date','—')} · líder {lead.get('name','—')} · retorno {fmt(lead.get('return_pct'),2,'%')} · alpha {fmt(lead.get('alpha_pct'),2,'%')} · max DD {fmt(lead.get('max_drawdown_pct'),2,'%')}")
        self.refresh()
    def fast(self):self.run('Decisión',safe_fast_cycle)
    def deep(self):self.run('Aprendizaje profundo',safe_deep_cycle)
    def reset(self):
        def job():reset_agents(200.0);reset_champion(200.0);return True
        self.run('Reinicio',job)
    def replay(self):self.run('Replay histórico',lambda:replay_historical(self.start.get().strip() or None,self.end.get().strip() or None,float(self.cash.get().replace(',','.'))))

    def _run_rows(self):
        c=con();rows=c.execute('select run_id,mode,status,start_date,end_date,created_at from simulation_runs order by created_at desc limit 8').fetchall();c.close();return rows
    def _episode_counts(self):
        c=con();rows=c.execute("select horizon,count(*),sum(case when outcome is not null then 1 else 0 end) from decision_episodes where agent_id='champion' group by horizon order by horizon").fetchall();c.close();return rows

    def export(self):
        try:
            os.makedirs(os.path.join(DATA,'exports'),exist_ok=True);stamp=__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S');base=os.path.join(DATA,'exports','radar_simulation_'+stamp);sim=simulation_summary_v3();mem=memory_health();learn=learning_v2_health();cp=champion_status();decision=champion_decision(record=False)
            payload={'generated_at':stamp,'simulation':sim,'memory':mem,'learning':learn,'champion_portfolio':cp,'champion_decision':decision,'real_trading':False}
            with open(base+'.json','w',encoding='utf-8') as f:json.dump(payload,f,ensure_ascii=False,indent=2,default=str)
            with open(base+'.csv','w',newline='',encoding='utf-8-sig') as f:
                w=csv.writer(f);w.writerow(['agent_id','name','return_pct','benchmark_return_pct','alpha_pct','max_drawdown_pct','sharpe','sortino','trades','costs'])
                for a in sim.get('agents',[]):w.writerow([a.get('agent_id'),a.get('name'),a.get('return_pct'),a.get('benchmark_return_pct'),a.get('alpha_pct'),a.get('max_drawdown_pct'),a.get('sharpe'),a.get('sortino'),a.get('trades'),a.get('costs')])
            self.last_export=base+'.json';self.status.set('Informe exportado · '+base+'.json')
        except Exception as e:self.status.set('Error exportando · '+str(e)[:100])

    def refresh(self):
        try:
            sts=agents_status();sim=simulation_summary_v3();mem=memory_health();learn=learning_v2_health();cp=champion_status();smap={x.get('agent_id'):x for x in sim.get('agents',[])}
            for i in self.tree.get_children():self.tree.delete(i)
            for a in sts:
                s=smap.get(a.get('agent_id'),{});self.tree.insert('', 'end',values=(a.get('name','?'),fmt(a.get('total'),2,' €'),fmt(a.get('pnl_pct'),2,'%'),fmt(a.get('invested'),2,' €'),fmt(s.get('max_drawdown_pct',a.get('max_drawdown_pct')),2,'%'),fmt(s.get('sharpe',a.get('sharpe')),2),fmt(s.get('sortino'),2),fmt(s.get('alpha_pct'),2,'%'),s.get('trades',len(a.get('trades',[]))),fmt(s.get('costs'),2,' €')))
            self.tree.insert('', 'end',values=('CHAMPION',fmt(cp.get('total'),2,' €'),fmt(cp.get('pnl_pct'),2,'%'),fmt(cp.get('invested'),2,' €'),fmt(cp.get('max_drawdown_pct'),2,'%'),fmt(cp.get('sharpe'),2),'—','—',len(cp.get('trades',[])),fmt(sum(float(x.get('costs') or 0) for x in cp.get('trades',[])),2,' €')))
            leader=sim.get('leader') or {};v3=sim.get('forward_v3') or {};self.simtxt.set(f"Run {sim.get('run_id','—')} · {sim.get('status','—')} · líder {leader.get('name','—')} · retorno {fmt(leader.get('return_pct'),2,'%')} · benchmark {fmt(leader.get('benchmark_return_pct'),2,'%')} · alpha {fmt(leader.get('alpha_pct'),2,'%')} · costes {fmt(leader.get('costs'),2,' €')}")
            self.audit.set(f"Benchmark actual {fmt(v3.get('benchmark_value'),2,' €')} · símbolos benchmark {v3.get('benchmark_symbols',0)} · operaciones importadas {v3.get('imported_trades',0)} · look-ahead {v3.get('lookahead',False)}")
            d=champion_decision(record=False);top=(d.get('candidates') or [{}])[0];self.champion.set(f"{d.get('action','ABSTAIN')} · {d.get('symbol') or '—'} · confianza calibrada {fmt((d.get('confidence') or 0)*100,1,'%')}");self.chportfolio.set(f"Cartera Champion {fmt(cp.get('total'),2,' €')} · P/L {fmt(cp.get('pnl_pct'),2,'%')} · efectivo {fmt(cp.get('cash'),2,' €')} · invertido {fmt(cp.get('invested'),2,' €')} · DD {fmt(cp.get('max_drawdown_pct'),2,'%')}")
            cal=d.get('calibration') or {};prof=cal.get('profile') or {};self.calibration.set(f"Confianza raw {fmt((d.get('raw_confidence') or 0)*100,1,'%')} → calibrada {fmt((d.get('calibrated_confidence') or 0)*100,1,'%')} · umbral ABSTAIN {fmt((d.get('abstain_threshold') or 0)*100,1,'%')} · evidencia calibración n={prof.get('n',0)} · error {fmt(prof.get('calibration_error'),3)}")
            rb=d.get('risk_budget') or {};self.chdetail.set(f"Score {fmt(top.get('champion_score'),3)} · consenso {fmt(top.get('consensus'),3)} · desacuerdo {fmt(d.get('disagreement'),3)} · memoria n={top.get('memory_n',0)} · asignación {fmt((d.get('allocation_fraction') or 0)*100,1,'%')} · factor DD {fmt(rb.get('drawdown_factor'),3)} · régimen {d.get('regime','—')}")
            mstats=mem.get('stats') or [];ms=next((x for x in mstats if x.get('scope')=='agent' and x.get('key')=='champion'),mstats[0] if mstats else {});self.memtxt.set(f"Episodios {mem.get('episodes',0)} · evaluados {mem.get('evaluated',0)} · hit-rate {fmt(ms.get('hit_rate'),3)} · recompensa media {fmt(ms.get('mean_reward'),3)} · error calibración {fmt(ms.get('calibration_error'),3)}")
            skills=learn.get('skills') or [];top_skill=skills[0] if skills else {};last=learn.get('last_cycle') or {};self.learntxt.set(f"Último ciclo {last.get('status','—')} · habilidades {len(skills)} · líder {top_skill.get('agent_id','—')} · score {fmt(top_skill.get('score'),3)} · n={top_skill.get('n','—')} · hit-rate {fmt(top_skill.get('hit_rate'),3)}")
            ec=self._episode_counts();self.evidence.set(' · '.join(f'{h}: {n} episodios / {ev or 0} evaluados' for h,n,ev in ec) if ec else 'Aún sin episodios Champion. Los horizontes shadow 1d, 1w y 3m se registran automáticamente; 1m gobierna la cartera paper.')
            self.runs.delete(0,'end')
            for run_id,mode,status,start,end,created in self._run_rows():self.runs.insert('end',f'{str(created)[:19]}  {run_id:<22} {mode:<10} {status:<10} {start or "—"} → {end or "—"}')
        except Exception as e:self.status.set('Error refrescando: '+str(e)[:100])
    def tick(self):
        if not self.busy:self.refresh()
        self.root.after(5000,self.tick)

def main():ensure_agents();champion_status();r=tk.Tk();Lab(r);r.mainloop()
if __name__=='__main__':main()
