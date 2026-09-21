from __future__ import annotations
import argparse, json
from pathlib import Path
from dataclasses import asdict
from ceo_core.windows_ops import WindowsPaths, WindowsPreflight, WindowsPackageInstaller, WindowsRepair


def main() -> int:
    p=argparse.ArgumentParser(description='CEO de IAs Windows lightweight operations')
    p.add_argument('--base',default='')
    sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('preflight')
    st=sub.add_parser('stage');st.add_argument('package');st.add_argument('--sha256',default='')
    pr=sub.add_parser('promote');pr.add_argument('--yes',action='store_true')
    rb=sub.add_parser('rollback');rb.add_argument('--yes',action='store_true')
    sub.add_parser('diagnostic')
    a=p.parse_args();paths=WindowsPaths(a.base or None)
    if a.cmd=='preflight':
        pre=WindowsPreflight(paths);print(json.dumps({'snapshot':asdict(pre.snapshot()),'install_plan':pre.install_plan()},indent=2));return 0
    if a.cmd=='diagnostic':print(json.dumps(WindowsRepair(paths).diagnostic(),indent=2));return 0
    inst=WindowsPackageInstaller(paths)
    if a.cmd=='stage':print(json.dumps(inst.stage_zip(Path(a.package),a.sha256 or None),indent=2));return 0
    if a.cmd=='promote':print(json.dumps(inst.promote_staged(human_confirmed=a.yes),indent=2));return 0
    if a.cmd=='rollback':print(json.dumps(inst.rollback_active(human_confirmed=a.yes),indent=2));return 0
    return 2
if __name__=='__main__':raise SystemExit(main())
