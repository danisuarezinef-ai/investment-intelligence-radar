from __future__ import annotations
from dataclasses import dataclass,asdict

@dataclass(slots=True)
class EvolutionScore:
    tests_passed:bool
    benchmark_gain:float
    security_regressions:int
    compatibility_regressions:int

class ReleaseEvolutionEngine:
    def recommendation(self,stable:EvolutionScore,challenger:EvolutionScore)->dict:
        eligible=challenger.tests_passed and challenger.security_regressions==0 and challenger.compatibility_regressions==0
        gain=challenger.benchmark_gain-stable.benchmark_gain
        promote=eligible and gain>.02
        return {'promote':promote,'eligible':eligible,'gain':round(gain,4),'reason':'measurable improvement with all gates' if promote else 'insufficient safe improvement'}
