#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from ceo_core.mobile_node import MobileNodeCore,MobileNodeConfig
c=MobileNodeCore(MobileNodeConfig())
ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True);sub.add_parser('list');a=sub.add_parser('approve');a.add_argument('id');r=sub.add_parser('reject');r.add_argument('id');args=ap.parse_args()
if args.cmd=='list':print(json.dumps(c.approvals.pending(),indent=2));raise SystemExit(0)
rows={x['id']:x for x in c.approvals.pending()};row=rows.get(args.id)
if not row:raise SystemExit('approval not pending/not found')
print(json.dumps(row,indent=2));phrase='APROBAR GASTO' if row['risk']=='spend' else 'APROBAR'
if args.cmd=='reject':phrase='RECHAZAR'
entered=input(f'Escribe exactamente {phrase!r} para confirmar: ')
if entered!=phrase:raise SystemExit('cancelled')
if args.cmd=='reject':c.approvals.reject(args.id,human_confirmed=True);print('REJECTED')
else:
 token=c.approvals.approve(args.id,human_confirmed=True);print('APPROVED one-shot token (copy only to the exact pending action):');print(token)
