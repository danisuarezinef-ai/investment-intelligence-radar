#!/usr/bin/env python3
"""LAN discovery helper. Mobile advertises by writing a signed pairing card; Windows can scan a user-provided subnet separately.
We avoid unauthenticated automatic trust: discovery finds candidates, pairing still requires the shared secret."""
from pathlib import Path
import json,socket,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from ceo_core.mobile_node import MobileNodeCore,MobileNodeConfig
core=MobileNodeCore(MobileNodeConfig());snap=vars(core.preflight.snapshot())
host=socket.gethostname();ips=[]
try:ips=socket.gethostbyname_ex(host)[2]
except Exception:pass
card={'node_id':core.config.node_id,'hostname':host,'ips':ips,'port':core.config.port,'snapshot':snap,'trusted':False,'pairing_required':True}
path=core.config.root_path/'discovery_card.json';path.write_text(json.dumps(card,indent=2));print(json.dumps(card,indent=2))
