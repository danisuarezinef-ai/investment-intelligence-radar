"""Cloud service v2 — exposes Part II validation/Decision Lab v5 read-only runtime view.

This wrapper preserves the existing cloud service loops and endpoints while adding
/validation-v2. It has no execution or promotion capability.
"""
import threading

import cloud_service as base
from radar_validation_runtime_v2 import validation_runtime_snapshot

REAL_TRADING = False
BaseHandler = base.MobileHandler


class ValidationHandler(BaseHandler):
    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/validation-v2':
            try:
                payload = validation_runtime_snapshot()
                payload['can_trade'] = False
                payload['auto_promote'] = False
                payload['real_trading'] = False
                self._send(200, payload)
            except Exception as exc:
                self._send(500, {
                    'ok': False,
                    'error': str(exc)[:800],
                    'can_trade': False,
                    'auto_promote': False,
                    'real_trading': False,
                })
            return
        super().do_GET()


base.run_worker._Handler = ValidationHandler


if __name__ == '__main__':
    threading.Thread(target=base.supabase_sync_loop, name='supabase-sync', daemon=True).start()
    threading.Thread(target=base.learning_sync_loop, name='learning-sync', daemon=True).start()
    threading.Thread(target=base.learning_loop, name='learning-engine', daemon=True).start()
    base.run_worker.main()
