"""Cloud service v3 — read-only unified validation runtime endpoint."""
import threading

import cloud_service_v2 as base_v2
from radar_validation_runtime_v3 import validation_runtime_v3

REAL_TRADING=False
BaseHandler=base_v2.ValidationHandler


class ValidationV3Handler(BaseHandler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/validation-v3':
            try:
                payload=validation_runtime_v3()
                payload['can_trade']=False
                payload['auto_promote']=False
                payload['real_trading']=False
                self._send(200,payload)
            except Exception as exc:
                self._send(500,{'ok':False,'error':str(exc)[:800],'can_trade':False,
                                'auto_promote':False,'real_trading':False})
            return
        super().do_GET()


base_v2.base.run_worker._Handler=ValidationV3Handler


if __name__=='__main__':
    base=base_v2.base
    threading.Thread(target=base.supabase_sync_loop,name='supabase-sync',daemon=True).start()
    threading.Thread(target=base.learning_sync_loop,name='learning-sync',daemon=True).start()
    threading.Thread(target=base.learning_loop,name='learning-engine',daemon=True).start()
    base.run_worker.main()
