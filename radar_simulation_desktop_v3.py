"""Simulation Lab v3: interactive v-score League cockpit.

Extends the Cloud-aware Lab with one compact visual card per PAPER competitor:
capital, risk, red/green equity sparkline, evidence-adjusted v-score gauge, dynamic
promotion readiness and explainable ETA. REAL_TRADING remains hard-disabled.
"""
from __future__ import annotations

import math

import radar_simulation_desktop_v2 as legacy

base = legacy.base
REAL_TRADING = False


def v_color(value):
    try: v=float(value)
    except (TypeError,ValueError): v=200.0
    if v < 120: return base.RED
    if v < 180: return '#f97316'
    if v < 220: return base.AMBER
    if v < 300: return base.GREEN
    return base.CYAN


def readiness_color(value):
    try: x=float(value)
    except (TypeError,ValueError): x=0.0
    if x < 35: return base.RED
    if x < 55: return '#f97316'
    if x < 75: return base.AMBER
    if x < 88: return base.GREEN
    return base.CYAN


def component_text(row,watch=None):
    row=row or {};watch=watch or {};c=row.get('v_components') or {}
    labels=(
        ('Calidad decisión','decision_quality'),
        ('Rendimiento/riesgo','risk_adjusted_return'),
        ('Control riesgo','risk_control'),
        ('Consistencia','consistency'),
        ('Generalización*','generalization'),
        ('Evidencia','evidence'),
    )
    parts=[f"{label}: {float(c.get(key) or 0):.0f}/100" for label,key in labels]
    parts.append(f"Confianza v: {float(row.get('v_confidence') or 0)*100:.0f}%")
    if watch:
        parts.append(f"Readiness: {float(watch.get('readiness') or 0):.0f}/100")
        parts.append(f"Ventaja v: {float(watch.get('v_gap') or 0):+.0f}")
        parts.append(f"Ventaja equity: {float(watch.get('equity_gap_pct') or 0):+.2f}%")
        parts.append(f"Evidencia común: {int(watch.get('common_days') or 0)}/{int(watch.get('dynamic_required_days') or 0)} jornadas dinámicas")
        parts.append(f"Riesgo: {'OK' if watch.get('risk_guard_ok') else 'BLOQUEADO'}")
        parts.append(str(watch.get('eta_text') or 'ETA indeterminada'))
    parts.append('* proxy conservador hasta disponer de evidencia por regímenes')
    parts.append('La v resume resultados PAPER observados; no es una garantía de rentabilidad futura.')
    return '   ·   '.join(parts)


def league_promotion_summary(league):
    league=league or {};watch=league.get('best_promotion_watch') or {}
    if not watch:
        return 'Velocímetros v calibrándose con evidencia PAPER real.'
    return (
        f"Más cerca del Champion: {watch.get('display_name','Challenger')} · "
        f"v{int(round(float(watch.get('v_score') or 200)))} vs "
        f"v{int(round(float(watch.get('champion_v_score') or 200)))} · "
        f"readiness {float(watch.get('readiness') or 0):.0f}/100 · "
        f"{watch.get('eta_text') or 'ETA indeterminada'}"
    )


def gauge_geometry(value,width=150,height=76):
    """Pure geometry helper used by UI and tests."""
    v=max(0.0,min(400.0,float(value or 0.0)))
    cx=width/2.0;cy=height-8.0;r=min(width*0.42,height*0.78)
    angle=math.pi-(v/400.0)*math.pi
    return {'cx':cx,'cy':cy,'r':r,'angle':angle,'x':cx+math.cos(angle)*r*0.82,'y':cy-math.sin(angle)*r*0.82,'v':v}


class VScoreLab(legacy.CloudAwareLab):
    def _league_widget(self,key):
        existing=self.league_widgets.get(key)
        if existing:return existing
        frame=base.tk.Frame(self.league_rows,bg=base.PANEL2,highlightthickness=1,highlightbackground=base.BORDER,padx=9,pady=7)
        frame.pack(fill='x',pady=(0,6))

        left=base.tk.Frame(frame,bg=base.PANEL2,width=330);left.pack(side='left',fill='y');left.pack_propagate(False)
        title=base.tk.StringVar(value=key);risk=base.tk.StringVar(value='RIESGO ?');capital=base.tk.StringVar(value='—');stats=base.tk.StringVar(value='—')
        base.tk.Label(left,textvariable=title,bg=base.PANEL2,fg=base.TEXT,font=('Segoe UI',10,'bold'),anchor='w').pack(fill='x')
        base.tk.Label(left,textvariable=risk,bg=base.PANEL2,fg=base.MUTED,font=('Segoe UI',8,'bold'),anchor='w').pack(fill='x',pady=(1,2))
        capital_label=base.tk.Label(left,textvariable=capital,bg=base.PANEL2,fg=base.CYAN,font=('Segoe UI',16,'bold'),anchor='w');capital_label.pack(fill='x')
        base.tk.Label(left,textvariable=stats,bg=base.PANEL2,fg=base.MUTED,font=('Segoe UI',8),anchor='w',justify='left').pack(fill='x',pady=(3,0))

        chart=base.tk.Canvas(frame,width=350,height=82,bg=base.PANEL2,highlightthickness=0,bd=0);chart.pack(side='left',fill='x',expand=True,padx=(8,10))

        gauge_box=base.tk.Frame(frame,bg=base.PANEL2,width=210);gauge_box.pack(side='right',fill='y');gauge_box.pack_propagate(False)
        top=base.tk.Frame(gauge_box,bg=base.PANEL2);top.pack(fill='x')
        vtxt=base.tk.StringVar(value='v200');vlabel=base.tk.Label(top,textvariable=vtxt,bg=base.PANEL2,fg=base.AMBER,font=('Segoe UI',17,'bold'),cursor='hand2');vlabel.pack(side='left')
        readiness=base.tk.StringVar(value='readiness —');base.tk.Label(top,textvariable=readiness,bg=base.PANEL2,fg=base.MUTED,font=('Segoe UI',8,'bold')).pack(side='right',pady=(7,0))
        gauge=base.tk.Canvas(gauge_box,width=190,height=74,bg=base.PANEL2,highlightthickness=0,bd=0,cursor='hand2');gauge.pack()
        eta=base.tk.StringVar(value='');base.tk.Label(gauge_box,textvariable=eta,bg=base.PANEL2,fg=base.MUTED,font=('Segoe UI',8),wraplength=200,justify='center').pack(fill='x')

        detail_frame=base.tk.Frame(self.league_rows,bg=base.PANEL,highlightthickness=1,highlightbackground=base.BORDER,padx=9,pady=7)
        detail=base.tk.StringVar(value='');base.tk.Label(detail_frame,textvariable=detail,bg=base.PANEL,fg=base.TEXT,font=('Segoe UI',8),wraplength=1120,justify='left').pack(fill='x')
        item={'frame':frame,'detail_frame':detail_frame,'title':title,'risk':risk,'capital':capital,'stats':stats,'canvas':chart,'gauge':gauge,'vtxt':vtxt,'vlabel':vlabel,'readiness':readiness,'eta':eta,'detail':detail,'row':{},'watch':{},'expanded':False,'display_v':200.0,'animation_id':0}
        self.league_widgets[key]=item
        vlabel.bind('<Button-1>',lambda _e,k=key:self._toggle_v_detail(k));gauge.bind('<Button-1>',lambda _e,k=key:self._toggle_v_detail(k))
        chart.bind('<Configure>',lambda _e,k=key:self._draw_league_chart(k))
        return item

    def _toggle_v_detail(self,key):
        item=self.league_widgets.get(key)
        if not item:return
        item['expanded']=not item.get('expanded',False)
        if item['expanded']:
            item['detail_frame'].pack(fill='x',pady=(0,6),after=item['frame'])
        else:
            item['detail_frame'].pack_forget()

    def _draw_gauge_now(self,item,value,readiness):
        canvas=item['gauge'];canvas.delete('all');w=max(canvas.winfo_width(),190);h=max(canvas.winfo_height(),74)
        box=(14,5,w-14,h*1.75)
        segments=((0,120,base.RED),(120,180,'#f97316'),(180,220,base.AMBER),(220,300,base.GREEN),(300,400,base.CYAN))
        for low,high,color in segments:
            start=180-(low/400.0)*180;extent=-((high-low)/400.0)*180
            canvas.create_arc(*box,start=start,extent=extent,style='arc',outline=color,width=7)
        g=gauge_geometry(value,w,h);canvas.create_line(g['cx'],g['cy'],g['x'],g['y'],fill=v_color(value),width=3)
        canvas.create_oval(g['cx']-4,g['cy']-4,g['cx']+4,g['cy']+4,fill=v_color(value),outline=base.TEXT)
        canvas.create_text(9,h-2,anchor='sw',text='0',fill=base.MUTED,font=('Segoe UI',7));canvas.create_text(w-9,h-2,anchor='se',text='400',fill=base.MUTED,font=('Segoe UI',7))
        ready=max(0.0,min(100.0,float(readiness or 0)));bar_y=h-2;canvas.create_line(35,bar_y,w-35,bar_y,fill=base.BORDER,width=3);canvas.create_line(35,bar_y,35+(w-70)*ready/100.0,bar_y,fill=readiness_color(ready),width=3)

    def _animate_gauge(self,key,target,readiness):
        item=self.league_widgets.get(key)
        if not item:return
        start=float(item.get('display_v',200.0));target=float(target or 200.0);item['animation_id']=int(item.get('animation_id',0))+1;animation_id=item['animation_id'];steps=10
        def frame(i):
            if item.get('animation_id')!=animation_id:return
            t=i/steps;ease=1-(1-t)*(1-t);value=start+(target-start)*ease;self._draw_gauge_now(item,value,readiness)
            if i<steps:
                try:self.root.after(24,lambda:frame(i+1))
                except Exception:pass
            else:item['display_v']=target
        frame(0)

    def _render_league(self):
        league=self.cloud_league or {};ranking=list(league.get('leaderboard') or []);watches={str(x.get('competitor_key')):x for x in (league.get('promotion_watch') or [])}
        self.league_promotion.set(league_promotion_summary(league))
        live=set()
        champion_key=str(league.get('champion_key') or 'champion')
        for row in ranking:
            key=str(row.get('competitor_key') or '');
            if not key:continue
            live.add(key);item=self._league_widget(key);watch=watches.get(key) or {};item['row']=row;item['watch']=watch
            role=str(row.get('league_role') or 'CHALLENGER');prefix='🏆 ' if key==champion_key else f"#{int(row.get('rank') or 0)} "
            item['title'].set(f"{prefix}{role} · {row.get('display_name',key)}")
            item['risk'].set(str(row.get('risk_label') or 'RIESGO ?'))
            capital=float(row.get('current_equity') or 0);change=row.get('period_change_pct');change_text='—' if change is None else f"{float(change):+.2f}%"
            item['capital'].set(f"{capital:,.2f} €   {change_text}".replace(',','X').replace('.',',').replace('X','.'))
            item['stats'].set(f"Aciertos {int(row.get('aciertos') or 0)} · Errores {int(row.get('errores') or 0)} · DD {float(row.get('max_drawdown_pct') or 0):.2f}% · invertido {float(row.get('invested_pct') or 0):.0f}%/{float(row.get('target_invested_pct') or 0):.0f}%")
            v=int(round(float(row.get('v_score') or 200)));trend=float(row.get('v_trend') or 0);arrow='↑' if trend>0 else ('↓' if trend<0 else '→')
            item['vtxt'].set(f"v{v} {arrow}");item['vlabel'].configure(fg=v_color(v))
            if key==champion_key:
                item['readiness'].set('CHAMPION');item['eta'].set(f"{row.get('v_band','')} · confianza {float(row.get('v_confidence') or 0)*100:.0f}%");ready=100.0
            else:
                ready=float(watch.get('readiness') or 0);item['readiness'].set(f"readiness {ready:.0f}/100");item['eta'].set(str(watch.get('eta_text') or 'Acumulando evidencia'))
            item['detail'].set(component_text(row,watch if key!=champion_key else None))
            self._draw_league_chart(key);self._animate_gauge(key,v,ready)
        for key,item in list(self.league_widgets.items()):
            if key not in live:
                item['frame'].pack_forget();item['detail_frame'].pack_forget()


def main():
    base.ensure_agents();base.champion_status();root=base.tk.Tk();VScoreLab(root);root.mainloop()


if __name__=='__main__':main()
