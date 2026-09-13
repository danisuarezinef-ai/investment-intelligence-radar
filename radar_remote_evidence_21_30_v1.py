"""Read-only durable Supabase evidence client for PAPER tasks 21-30.

The Edge endpoint uses direct DB access and custom x-radar-token auth. This client never
writes evidence, backfills outcomes, submits orders, or grants promotion/release authority.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from radar_supabase_sync import SYNC_TOKEN, SYNC_URL

REAL_TRADING=False
DEFAULT_URL='https://wvmiludqzdepqmjhfwos.supabase.co/functions/v1/radar-paper-evidence-21-30'
HTTP_TIMEOUT_SECONDS=35


def _url():
    explicit=os.environ.get('SUPABASE_PAPER_EVIDENCE_21_30_URL','').strip()
    if explicit:return explicit
    base=(SYNC_URL or '').strip()
    if '/radar-sync' in base:return base.rsplit('/radar-sync',1)[0]+'/radar-paper-evidence-21-30'
    return DEFAULT_URL


def configured():return bool(_url() and SYNC_TOKEN)


def summary(timeout=HTTP_TIMEOUT_SECONDS):
    if not configured():return {'ok':False,'status':'NOT_CONFIGURED','real_trading':False}
    req=urllib.request.Request(_url(),data=b'{"action":"summary"}',method='POST',headers={
        'Content-Type':'application/json','X-Radar-Token':SYNC_TOKEN,
        'User-Agent':'InvestmentIntelligenceRadarPaperEvidence2130/1'})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            out=json.loads(response.read().decode('utf-8'))
        out['real_trading']=False
        return out
    except (urllib.error.URLError,urllib.error.HTTPError,TimeoutError,OSError,ValueError) as exc:
        return {'ok':False,'status':'FAIL_CLOSED','error':f'{type(exc).__name__}: {str(exc)[:500]}',
                'real_trading':False}
