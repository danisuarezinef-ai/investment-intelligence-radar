#!/usr/bin/env python3
from pathlib import Path
import argparse,json,os,secrets,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from ceo_core.mobile_node import MobileNodeCore,MobileNodeConfig
ap=argparse.ArgumentParser();ap.add_argument('--windows-name',default='windows-ceo');ap.add_argument('--windows-url',default='');a=ap.parse_args()
core=MobileNodeCore(MobileNodeConfig());token=os.getenv('CEO_MOBILE_SHARED_SECRET') or secrets.token_urlsafe(32)
core.db.set_meta('paired_windows',{'name':a.windows_name,'url':a.windows_url,'paired':True,'secret_value_persisted':False})
print(json.dumps({'paired':True,'windows_name':a.windows_name,'windows_url':a.windows_url,'shared_secret':token,'warning':'Copy this secret once to the Windows environment; it is NOT stored in the mobile database.'},indent=2))
