"""Pure, headless-testable state helpers for the canonical desktop UI."""

import re


def version_key(value):
    """Return a comparable numeric version tuple (supports an optional leading v)."""
    text = str(value or '').strip()
    if text.lower().startswith('v'):
        text = text[1:]
    if not re.fullmatch(r'\d+(?:\.\d+)*', text):
        raise ValueError('versión no válida')
    parts = tuple(int(part) for part in text.split('.'))
    return parts + (0,) * (3 - len(parts))


def update_available(local_version, remote_version):
    return version_key(remote_version) > version_key(local_version)


def switch_view(enabled=None, busy=False):
    if busy:
        return {'text': 'OFF | ON', 'state': 'CAMBIANDO', 'selected': None}
    if enabled is None:
        return {'text': 'OFF | ON', 'state': 'SIN CONEXIÓN', 'selected': None}
    return {
        'text': 'OFF  ●' if not enabled else '●  ON',
        'state': 'ACTIVO' if enabled else 'DETENIDO',
        'selected': bool(enabled),
    }

