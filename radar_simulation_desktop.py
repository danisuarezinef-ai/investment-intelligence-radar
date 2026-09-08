import threading
import tkinter as tk
from tkinter import ttk

from radar_agents import ensure_agents, agents_status, reset_agents
from radar_simulation_v2 import simulation_summary, replay_historical
from radar_decision_memory_v2 import memory_health
from radar_learning_v2 import learning_v2_health
from radar_meta_decision_v2 import champion_decision
from radar_runtime_v2 import safe_fast_cycle, safe_deep_cycle

REAL_TRADING=False
APP_VERSION='1.4.0'
BG='#0f172a'; PANEL='#1e293b'; PANEL2='#111827'; TEXT='#f8fafc'; MUTED='#94a3b8'; GREEN='#16a34a'; BLUE='#2563eb'; BORDER='#334155'; CYAN='#22d3ee'

def fmt(v,d=2,s=''):
    try:return f'{float(v):.{d}f}{s}'
    except Exception:return '—'

def card(p):return tk.Frame(p,bg=PANEL,highlightthickness=1,highlightbackground=BORDER,padx=14,pady=12)

def lbl(p,t='',fg=TEXT,size=9,bold=False):return tk.Label(p,text=t,bg=p.cget('bg'),fg=fg,font=('Segoe UI',size,'bold' if bold else 'normal'),justify='left')

class Lab:
    def __init__(self,root):
        self.root=root; self.busy=False
        root.title('Investment Intelligence Radar · Simulation Lab'); root.geometry('1280x900'); root.minsize(1020,700); root.configure(bg=BG)
        cv=tk.Canvas(root,bg=BG,highlightthickness=0); sb=tk.Scrollbar(root,orient='vertical',command=cv.yview); cv.configure(yscrollcommand=sb.set); sb.pack(side='right',fill='y'); cv.pack(side='left',fill='both',expand=True)
        self.main=tk.Frame(cv,bg=BG,padx=24,pady=20); wid=cv.create_window((0,0),window=self.main,anchor='nw'); cv.bind('<Configure>',lambda e:cv.itemconfigure(wid,width=e.width)); self.main.bind('<Configure>',lambda e:cv.configure(scrollregion=cv.bbox('all')))
        self.build(); ensure_agents(); self.refresh(); root.after(5000,self.tick)
    def build(self):
        lbl(self.main,'Simulation Lab',size=24,bold=True).pack(anchor='w'); lbl(self.main,f'5 agentes + Champion adaptativo · Windows v{APP_VERSION} · TRADING REAL OFF',MUTED,10).pack(anchor='w',pady=(0,12))
        c=card(self.main); c.pack(fill='x',pady=(0,10)); lbl(c,'Control de simulación',size=12,bold=True).pack(side='left'); self.status=tk.StringVar(value='Listo'); tk.Label(c,textvariable=self.status,bg=PANEL,fg=CYAN,font=('Segoe UI',9,'bold')).pack(side='left',padx=14)
        for text,cmd in [('DECIDIR AHORA',self.fast),('APRENDIZAJE PROFUNDO',self.deep),('REINICIAR 200 € / AGENTE',self.reset)]: tk.Button(c,text=text,command=cmd,bg=BLUE if text=='DECIDIR AHORA' else PANEL2,fg='white',relief='flat',bd=0,padx=12,pady=7).pack(side='right',padx=4)
        ch=card(self.main); ch.pack(fill='x',pady=(0,10)); lbl(ch,'Champion adaptativo',size=13,bold=True).pack(anchor='w'); self.champion=tk.StringVar(value='—'); self.chdetail=tk.StringVar(value='—'); tk.Label(ch,textvariable=self.champion,bg=PANEL,fg=GREEN,font=('Segoe UI',16,'bold')).pack(anchor='w',pady=(6,2)); tk.Label(ch,textvariable=self.chdetail,bg=PANEL,fg=MUTED,font=('Segoe UI',9),wraplength=1120,justify='left').pack(anchor='w')
        a=card(self.main); a.pack(fill='x',pady=(0,10)); lbl(a,'Agentes simulados',size=13,bold=True).pack(anchor='w'); cols=('agente','total','pnl','invertido','drawdown','sharpe','trades'); self.tree=ttk.Treeview(a,columns=cols,show='headings',height=6)
        for c,h,w in [('agente','Agente',180),('total','Capital',110),('pnl','P/L',110),('invertido','Invertido',110),('drawdown','Max DD',100),('sharpe','Sharpe',90),('trades','Operaciones',90)]: self.tree.heading(c,text=h); self.tree.column(c,width=w,anchor='w' if c=='agente' else 'center')
        self.tree.pack(fill='x',pady=(8,0))
        s=card(self.main); s.pack(fill='x',pady=(0,10)); lbl(s,'Forward Simulation v2',size=12,bold=True).pack(anchor='w'); self.simtxt=tk.StringVar(value='—'); tk.Label(s,textvariable=self.simtxt,bg=PANEL,fg=TEXT,font=('Segoe UI',10),wraplength=1120,justify='left').pack(anchor='w',pady=(5,0))
        row=tk.Frame(self.main,bg=BG); row.pack(fill='x',pady=(0,10)); m=card(row); m.pack(side='left',fill='both',expand=True,padx=(0,5)); l=card(row); l.pack(side='left',fill='both',expand=True,padx=(5,0)); lbl(m,'Memoria de decisiones',size=12,bold=True).pack(anchor='w'); lbl(l,'Aprendizaje',size=12,bold=True).pack(anchor='w'); self.memtxt=tk.StringVar(value='—'); self.learntxt=tk.StringVar(value='—'); tk.Label(m,textvariable=self.memtxt,bg=PANEL,fg=TEXT,font=('Segoe UI',9),wraplength=520,justify='left').pack(anchor='w',pady=(6,0)); tk.Label(l,textvariable=self.learntxt,bg=PANEL,fg=TEXT,font=('Segoe UI',9),wraplength=520,justify='left').pack(anchor='w',pady=(6,0))
        r=card(self.main); r.pack(fill='x',pady=(0,10)); lbl(r,'Replay histórico point-in-time',size=12,bold=True).pack(anchor='w'); rr=tk.Frame(r,bg=PANEL); rr.pack(fill='x',pady=(7,5)); self.start=tk.StringVar(); self.end=tk.StringVar(); self.cash=tk.StringVar(value='200')
        for t,v,w in [('Inicio YYYY-MM-DD',self.start,15),('Fin YYYY-MM-DD',self.end,15),('Capital/agente',self.cash,10)]: lbl(rr,t,MUTED,8).pack(side='left',padx=(0,4)); tk.Entry(rr,textvariable=v,width=w,bg=PANEL2,fg=TEXT,insertbackground=TEXT,relief='flat').pack(side='left',padx=(0,10),ipady=5)
        tk.Button(rr,text='EJECUTAR REPLAY',command=self.replay,bg=BLUE,fg='white',relief='flat',bd=0,padx=14,pady=7).pack(side='right'); self.replaytxt=tk.StringVar(value='Sin look-ahead: cada decisión usa sólo información disponible hasta esa fecha.'); tk.Label(r,textvariable=self.replaytxt,bg=PANEL,fg=MUTED,font=('Segoe UI',9),wraplength=1120,justify='left').pack(anchor='w')
        lbl(self.main,'Los resultados simulados no implican rendimiento futuro. Trading real permanece desactivado.',MUTED,9).pack(anchor='w')
    def run(self,name,fn):
        if self.busy:return
        self.busy=True; self.status.set(name+'…')
        def work():
            try:res=fn(); self.root.after(0,lambda:self.done(name,res,None))
            except Exception as e:self.root.after(0,lambda:self.done(name,None,e))
        threading.Thread(target=work,daemon=True).start()
    def done(self,name,res,err): self.busy=False; self.status.set(('ERROR · '+str(err)[:90]) if err else name+' completado'); self.refresh()
    def fast(self): self.run('Decisión',safe_fast_cycle)
    def deep(self): self.run('Aprendizaje profundo',safe_deep_cycle)
    def reset(self): self.run('Reinicio',lambda:reset_agents(200.0))
    def replay(self): self.run('Replay histórico',lambda:replay_historical(self.start.get().strip() or None,self.end.get().strip() or None,float(self.cash.get().replace(',','.'))))
    def refresh(self):
        try:
            sts=agents_status(); sim=simulation_summary(); mem=memory_health(); learn=learning_v2_health(); smap={x.get('agent_id'):x for x in sim.get('agents',[])}
            for i in self.tree.get_children():self.tree.delete(i)
            for a in sts:
                s=smap.get(a.get('agent_id'),{}); self.tree.insert('', 'end', values=(a.get('name','?'),fmt(a.get('total'),2,' €'),fmt(a.get('pnl_pct'),2,'%'),fmt(a.get('invested'),2,' €'),fmt(s.get('max_drawdown_pct',a.get('max_drawdown_pct')),2,'%'),fmt(s.get('sharpe',a.get('sharpe')),2),s.get('trades',len(a.get('trades',[])))))
            leader=sim.get('leader') or {}; self.simtxt.set(f"Run {sim.get('run_id','—')} · {sim.get('status','—')} · líder {leader.get('name','—')} · retorno {fmt(leader.get('return_pct'),2,'%')} · alpha {fmt(leader.get('alpha_pct'),2,'%')} · costes {fmt(leader.get('costs'),2,' €')}")
            d=champion_decision(record=False); self.champion.set(f"{d.get('action','ABSTAIN')} · {d.get('symbol') or '—'} · confianza {fmt((d.get('confidence') or 0)*100,1,'%')}"); self.chdetail.set(f"Score {fmt(d.get('score'),3)} · desacuerdo {fmt(d.get('disagreement'),3)} · familias independientes {d.get('independent_families','—')} · ABSTAIN habilitado")
            self.memtxt.set(f"Episodios {mem.get('episodes',0)} · evaluados {mem.get('evaluated',0)} · hit-rate {fmt(mem.get('hit_rate'),3)} · recompensa {fmt(mem.get('mean_reward'),3)} · calibración {fmt(mem.get('calibration_error'),3)}")
            skills=learn.get('agent_skills') or []; top=skills[0] if skills else {}; self.learntxt.set(f"Ciclos {learn.get('cycles',0)} · observaciones {learn.get('observations',0)} · mejor habilidad {top.get('agent_id','—')} ({fmt(top.get('skill'),3)}) · trading real OFF")
        except Exception as e:self.status.set('Error refrescando: '+str(e)[:90])
    def tick(self):
        if not self.busy:self.refresh()
        self.root.after(5000,self.tick)

def main(): ensure_agents(); r=tk.Tk(); Lab(r); r.mainloop()
if __name__=='__main__': main()
