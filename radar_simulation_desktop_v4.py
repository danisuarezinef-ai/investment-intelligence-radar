"""Simulation Lab v4: v-score cockpit plus live PAPER portfolio explainability.

Durable league evidence/ranking remains authoritative. Live holdings and recent
PAPER decisions are attached only for human inspection. REAL_TRADING is disabled.
"""
from __future__ import annotations

import radar_simulation_desktop_v3 as cockpit

base = cockpit.base
REAL_TRADING = False


def _eur(value):
    try:
        return f"{float(value):,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.')
    except (TypeError, ValueError):
        return '—'


def _pct(value):
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return '—'


def live_detail_text(detail):
    """Human-readable current portfolio and decision trace for an expanded card."""
    detail = detail or {}
    if not detail:
        return 'Cartera PAPER en vivo: detalle no disponible todavía.'
    lines = [
        'CARTERA PAPER EN VIVO · solo observación',
        f"Efectivo {_eur(detail.get('cash'))} · invertido {_eur(detail.get('invested'))} · exposición {float(detail.get('invested_pct') or 0):.0f}% · equity {_eur(detail.get('equity'))}",
    ]
    positions = list(detail.get('positions') or [])
    if positions:
        rendered = []
        for row in positions[:6]:
            rendered.append(
                f"{row.get('symbol','?')} {_eur(row.get('value'))} ({_pct(row.get('pnl_pct'))}; "
                f"media {_eur(row.get('avg_price'))} → {_eur(row.get('price'))})"
            )
        lines.append('Posiciones: ' + ' · '.join(rendered))
    else:
        lines.append('Posiciones: ninguna · capital actualmente en efectivo.')
    decisions = list(detail.get('recent_decisions') or [])
    if decisions:
        rendered = []
        for row in decisions[:4]:
            reason = str(row.get('reason') or '').strip().replace('\n', ' ')[:95]
            stamp = str(row.get('ts') or '')[:16].replace('T', ' ')
            item = f"{row.get('side','?')} {row.get('symbol','?')} {_eur(row.get('value'))}"
            if reason:
                item += f" · {reason}"
            if stamp:
                item += f" · {stamp}"
            rendered.append(item)
        lines.append('Últimas decisiones: ' + ' | '.join(rendered))
    else:
        lines.append('Últimas decisiones: todavía no hay operaciones registradas.')
    lines.append('Esta telemetría no modifica v-score, promoción ni gobernanza; la autoridad durable sigue en la Liga PAPER.')
    return '\n'.join(lines)


class ExplainableVScoreLab(cockpit.VScoreLab):
    def _render_league(self):
        super()._render_league()
        league = self.cloud_league or {}
        details = (((self.cloud_simulator or {}).get('competitor_details') or {}).get('competitors') or {})
        watches = {str(x.get('competitor_key')): x for x in (league.get('promotion_watch') or [])}
        champion_key = str(league.get('champion_key') or 'champion')
        for key, item in self.league_widgets.items():
            row = item.get('row') or {}
            if not row:
                continue
            watch = watches.get(key) or {}
            durable = cockpit.component_text(row, watch if key != champion_key else None)
            live = live_detail_text(details.get(key) or {})
            item['detail'].set(durable + '\n\n' + live)


def main():
    base.ensure_agents()
    base.champion_status()
    root = base.tk.Tk()
    ExplainableVScoreLab(root)
    root.mainloop()


if __name__ == '__main__':
    main()
