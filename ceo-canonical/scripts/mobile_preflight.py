#!/usr/bin/env python3
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from ceo_core.mobile_node import MobileNodeCore,MobileNodeConfig
core=MobileNodeCore(MobileNodeConfig());snap=core.preflight.snapshot(probe_network=True)
print(json.dumps({'preflight':vars(snap),'model_tiers':core.preflight.model_tiers(snap),'certification':core.certification()},indent=2,ensure_ascii=False))
