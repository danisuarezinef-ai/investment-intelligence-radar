"""Pure presentation helpers for the Decision v2 desktop panel."""

def decision_v2_lines(snapshot):
    d=(snapshot or {}).get('decision_v2') or {}
    if not d:
        return ['Decision v2 · sin datos todavía']
    if not d.get('ok', True):
        return ['Decision v2 · ERROR · '+str(d.get('error','desconocido'))[:120]]
    lines=[]
    champ=d.get('champion') or d.get('adaptive_champion') or {}
    if champ:
        lines.append('CHAMPION · '+str(champ.get('action') or champ.get('name') or champ.get('policy') or 'activo'))
    for key,label in [('simulation','Simulación'),('memory','Memoria'),('learning','Aprendizaje')]:
        x=d.get(key)
        if isinstance(x,dict):
            state=x.get('status') or x.get('state') or x.get('count') or x.get('episodes') or 'activo'
            lines.append(f'{label} · {state}')
    lines.append('Trading real · OFF')
    return lines or ['Decision v2 · activo · Trading real OFF']
