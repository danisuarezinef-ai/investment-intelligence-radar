import threading
import radar_core

_lock=threading.RLock()
_original=radar_core.write_status


def safe_write_status(**kwargs):
    with _lock:
        return _original(**kwargs)


def install(run_worker_module=None):
    radar_core.write_status=safe_write_status
    if run_worker_module is not None:
        run_worker_module.write_status=safe_write_status
    return safe_write_status
