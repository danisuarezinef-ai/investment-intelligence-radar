#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from ceo_core.mobile_node import MobileNodeCore,MobileNodeConfig,MobileGitWorkspace
c=MobileNodeCore(MobileNodeConfig());ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True);sub.add_parser('dashboard');sub.add_parser('stop');sub.add_parser('resume');rv=sub.add_parser('review');rv.add_argument('path');args=ap.parse_args()
if args.cmd=='dashboard':print(json.dumps(c.dashboard(),indent=2));raise SystemExit(0)
if args.cmd=='stop':print(json.dumps(c.emergency_stop('mobile human emergency stop'),indent=2));raise SystemExit(0)
if args.cmd=='resume':
 if input("Escribe 'REANUDAR' para Safe Resume: ")!='REANUDAR':raise SystemExit('cancelled')
 print(json.dumps(c.safe_resume(human_confirmed=True),indent=2));raise SystemExit(0)
if args.cmd=='review':
 g=MobileGitWorkspace(Path(args.path));print('STATUS\n',g.status()['stdout']);print('DIFF\n',g.diff()['stdout']);print('LOG\n',g.log()['stdout'])
