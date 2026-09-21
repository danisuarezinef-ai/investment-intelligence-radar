#!/usr/bin/env python3
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from ceo_core.mobile_node import MobileBenchmark,MobileNodeCore,MobileNodeConfig
core=MobileNodeCore(MobileNodeConfig());print(json.dumps({'cpu_hash':MobileBenchmark().run(),'preflight':vars(core.preflight.snapshot()),'model_healthy':core.worker.client.health()},indent=2))
