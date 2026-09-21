from __future__ import annotations
from collections import deque
from dataclasses import dataclass, replace

ANDROID_ORDER=('NO_ARTIFACT','BUILT','ADMITTED','API35','API36','RUNTIME_ACCEPTED')
WINDOWS_ORDER=('PLAN','STARTED','VERIFIED')

@dataclass(frozen=True)
class CrossStateV8:
    android:str='NO_ARTIFACT'; windows:str='PLAN'; human_start:bool=False; human_release:bool=False; blocked:bool=False

EVENTS=('build','admit','api35','api36','runtime_accept','human_start','windows_start','windows_verify','human_release')

def step_v8(s:CrossStateV8,e:str)->tuple[CrossStateV8,bool,str]:
    if s.blocked:return s,False,'blocked'
    if e=='human_start': return replace(s,human_start=True),True,'ok'
    if e=='human_release':
        if s.android!='RUNTIME_ACCEPTED' or s.windows!='VERIFIED': return replace(s,blocked=True),False,'release_without_complete_evidence'
        return replace(s,human_release=True),True,'ok'
    amap={'build':'BUILT','admit':'ADMITTED','api35':'API35','api36':'API36','runtime_accept':'RUNTIME_ACCEPTED'}
    if e in amap:
        target=amap[e]
        if ANDROID_ORDER.index(target)!=ANDROID_ORDER.index(s.android)+1:return replace(s,blocked=True),False,'android_non_monotonic'
        return replace(s,android=target),True,'ok'
    if e=='windows_start':
        if not s.human_start or s.android!='RUNTIME_ACCEPTED' or s.windows!='PLAN': return replace(s,blocked=True),False,'unsafe_windows_start'
        return replace(s,windows='STARTED'),True,'ok'
    if e=='windows_verify':
        if s.windows!='STARTED': return replace(s,blocked=True),False,'windows_verify_without_start'
        return replace(s,windows='VERIFIED'),True,'ok'
    return replace(s,blocked=True),False,'unknown_event'

def bounded_model_check_v8(max_depth:int=12)->dict:
    q=deque([(CrossStateV8(),0)]); seen={CrossStateV8()}; transitions=0; violations=[]
    while q:
        s,d=q.popleft()
        if d>=max_depth:continue
        for e in EVENTS:
            ns,ok,reason=step_v8(s,e); transitions+=1
            if ok:
                if ns.human_release and (ns.android!='RUNTIME_ACCEPTED' or ns.windows!='VERIFIED'): violations.append('release_without_complete_evidence')
                if ns.windows in {'STARTED','VERIFIED'} and not ns.human_start: violations.append('windows_without_human_start')
                if ns.windows in {'STARTED','VERIFIED'} and ns.android!='RUNTIME_ACCEPTED': violations.append('windows_before_android_acceptance')
                if ns not in seen: seen.add(ns); q.append((ns,d+1))
            elif not ns.blocked and reason!='blocked': violations.append('failure_not_blocked')
    return {'schema_version':8,'ok':not violations,'states_explored':len(seen),'transitions_checked':transitions,
            'violations':sorted(set(violations)),'truncated':False}
