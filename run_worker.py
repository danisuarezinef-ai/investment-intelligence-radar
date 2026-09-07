import os, time, traceback
from radar_core import init_db, collect_market, collect_sec, collect_science, write_status, PID, LOG, now

def main():
    init_db(); open(PID,'w').write(str(os.getpid()))
    write_status(version='1.0.0',state='INICIANDO',started_at=now(),last_error='')
    next_market=next_sec=next_science=0
    try:
        while True:
            t=time.time(); write_status(state='ACTIVO')
            try:
                if t>=next_market: write_status(state='RECOPILANDO MERCADO',current_job='market'); collect_market(); next_market=t+300
                if t>=next_sec: write_status(state='RECOPILANDO SEC',current_job='sec'); collect_sec(); next_sec=t+900
                if t>=next_science: write_status(state='RECOPILANDO CIENCIA',current_job='science'); collect_science(); next_science=t+1800
            except Exception as e:
                with open(LOG,'a',encoding='utf-8') as f: f.write(traceback.format_exc()+'\n')
                write_status(state='ERROR',last_error=str(e))
            write_status(state='ESPERANDO SIGUIENTE CICLO',current_job='')
            time.sleep(10)
    finally:
        try: os.remove(PID)
        except OSError: pass

if __name__=='__main__': main()
