"""Deterministic owned schemas; labels are scientific case identifiers."""
from __future__ import annotations
import copy,json
from pathlib import Path

def i(op,**kw):return {'op':op,**kw}
def read(b,o=0):return {'read':[b,o]}
def length(b='a',o=0,out='n'):return i('strlen',buf=b,off=o,out=out)
def emit(v='$n'):return i('emit',value=v)
def case(family,variables,buffers,reference,candidate=None,expected='equivalent'):
    return {'id':'','family':family,'variables':variables,'buffers':buffers,'reference':reference,'candidate':copy.deepcopy(reference if candidate is None else candidate),'expected':expected}
def build():
    cases=[]
    for n in (3,4,8,16,32,64):
        a=['@x','@y',0]+[17]*(n-3);b=[5]*n
        prefix=[i('switch',buf='a')]
        families=[
            ('length',[length(),emit()],{'a':a}),
            ('find_zero',[i('strchr',buf='a',off=0,char=0,out='n'),emit()],{'a':a}),
            ('find_literal',[i('strchr',buf='a',off=0,char=1,out='n'),emit()],{'a':a}),
            ('unsigned_compare',[i('strcmp',a='a',ao=0,b='b',bo=0,out='n'),emit()],{'a':['@x',0]+[17]*(n-2),'b':['@y',0]+[17]*(n-2)}),
            ('copy',[i('strcpy',src='a',so=0,dst='b',do=0),length('b'),emit()],{'a':a,'b':b}),
            ('concatenate',[i('strcat',src='a',so=0,dst='b',do=0),length('b'),emit()],{'a':['@x',0]+[17]*(n-2),'b':['@y',0]+[17]*(n-2)}),
            ('overlap_move',[i('memmove',src='a',so=0,dst='a',do=1,n=2),length(),emit()],{'a':a}),
            ('symbolic_offset',[length(),i('store',buf='a',off='$n',value=0),length(),emit()],{'a':a}),
            ('high_mask',[i('mask_eq',value=read('a'),mask=128,equal=0,out='g'),i('assume',value='$g'),length(),emit()],{'a':a}),
            ('scalar_wrap',[length(),i('scalar',fn='add',left='$n',right=255,width=8,out='n'),emit()],{'a':a}),
        ]
        for family,p,bufs in families:cases.append(case(family,['x','y'],bufs,p,[i('switch',buf=b) for b in bufs]+p))
    # Context-sensitive erasure: the same lossy view is safe read-only, unsafe
    # after the first NUL is overwritten, and safe after the tail is repaired.
    a=[0,'@x',0]
    p=[length(),emit()]
    cases.append(case('erasure_read_only',['x'],{'a':a},p,[i('erase_tail',buf='a')]+p))
    p=[i('store',buf='a',off=0,value=1),length(),emit()]
    cases.append(case('erasure_exposure',['x'],{'a':a},p,[i('erase_tail',buf='a')]+p,'different'))
    p=[i('store',buf='a',off=1,value=0),i('store',buf='a',off=0,value=1),length(),emit()]
    cases.append(case('erasure_repair',['x'],{'a':a},p,[i('erase_tail',buf='a')]+p))
    p=[i('strchr',buf='a',off=0,char=0,out='n'),emit()];q=copy.deepcopy(p);q[0]['op']='strchr_no_zero'
    cases.append(case('omit_terminator_search',['x'],{'a':['@x',0]},p,q,'different'))
    p=[i('strcmp',a='a',ao=0,b='b',bo=0,out='n'),emit()];q=copy.deepcopy(p);q[0]['op']='strcmp_signed'
    cases.append(case('signed_order',['x','y'],{'a':['@x',0],'b':['@y',0]},p,q,'different'))
    guards=[i('mask_eq',value=read('a'),mask=128,equal=0,out='g'),i('assume',value='$g'),i('mask_eq',value=read('b'),mask=128,equal=0,out='h'),i('assume',value='$h')]
    cases.append(case('signed_order_guarded',['x','y'],{'a':['@x',0],'b':['@y',0]},guards+p,guards+q))
    p=[i('strcpy',dst='b',do=0,src='a',so=0),length('b'),emit()];q=copy.deepcopy(p);q[0]['op']='copy_no_zero'
    cases.append(case('omit_copy_terminator',['x'],{'a':['@x',0],'b':[1,1,0]},p,q,'different'))
    cases.append(case('omit_copy_redundant',['x'],{'a':['@x',0],'b':[0,0,0]},p,q))
    p=[i('memmove',src='a',so=0,dst='a',do=1,n=2),length(),emit()];q=copy.deepcopy(p);q[0]['op']='move_forward'
    cases.append(case('move_direction',['x','y'],{'a':['@x','@y',0,0]},p,q,'different'))
    p=[i('memmove',src='a',so=0,dst='a',do=2,n=2),length(o=2),emit()];q=copy.deepcopy(p);q[0]['op']='move_forward'
    cases.append(case('move_direction_disjoint',['x'],{'a':['@x',0,0,0]},p,q))
    p=[i('strlen_cached',buf='a',off=0,out='old'),i('store',buf='a',off=1,value=1),i('strlen_cached',buf='a',off=0,out='n'),emit()]
    q=copy.deepcopy(p);q[1]['op']='store_stale'
    cases.append(case('alias_invalidation',['x','y'],{'a':['@x',0,'@y',0]},p,q,'different'))
    p=[length(),i('scalar_eq',left='$n',right=1,out='g'),i('assume',value='$g'),length(),emit()]
    q=copy.deepcopy(p);q[-2]=i('const',value=1,out='n')
    cases.append(case('guarded_rewrite',['x','y'],{'a':['@x','@y',0]},p,q))
    cases.append(case('dropped_guard',['x','y'],{'a':['@x','@y',0]},p,[i('const',value=1,out='n'),emit()],'different'))
    p=[length(),emit()];q=[i('strlen_capacity',buf='a',off=0,out='n'),emit()]
    cases.append(case('unterminated_accepted',['x','y'],{'a':['@x','@y']},p,q,'different'))
    # Boundary and falsification cases are included regardless of result.
    for a,label in [([0,None],'uninitialized_tail'),([None,0],'uninitialized_prefix'),([None,None],'uninitialized_all')]:
        p=[length(),emit()];cases.append(case(label,[],{'a':a},p,[i('switch',buf='a')]+p))
    for n in (0,1,3,4):
        p=[i('memmove',src='a',so=3,dst='a',do=3,n=n),length(),emit()]
        cases.append(case('move_bounds',[],{'a':[1,0,None]},p))
    for offset in (-1,0,1,2,3):
        p=[length(o=offset),emit()];cases.append(case('scan_bounds',['x'],{'a':['@x',0]},p))
    for width in (1,8,16,32,64):
        for fn in ('add','sub','shl','lshr'):
            p=[length(),i('scalar',fn=fn,left='$n',right=width,width=width,out='n'),emit()]
            cases.append(case('scalar_width',['x'],{'a':['@x',0]},p,[i('switch',buf='a')]+p))
    p=[i('mask_eq',value=read('a'),mask=1,equal=0,out='g'),i('assume',value='$g'),length(),emit()]
    cases.append(case('low_bit_mask',['x'],{'a':['@x',0]},p))
    for m in (1,2,3,4,5,6):
        vs=['x'+str(j) for j in range(m)];a=['@'+v for v in vs]+[0]
        p=[length(),emit()]
        cases.append(case('support_scaling',vs,{'a':a},p,[i('switch',buf='a')]+p))
        chain=[i('byte_eq',left=read('a'),right=0,out='z'),i('scalar_eq',left='$z',right=0,out='g'),i('assume',value='$g')]
        for j in range(m-1):chain += [i('byte_lt',left=read('a',j),right=read('a',j+1),out='g'),i('assume',value='$g')]
        chain += [length(),emit()]
        cases.append(case('strict_chain',vs,{'a':a},chain))
    # Aliased-copy precondition excludes overlapping access regions.
    for dst in (0,1,2,3):
        p=[i('strcpy',src='a',so=0,dst='a',do=dst),length(),emit()]
        cases.append(case('copy_overlap',['x'],{'a':['@x',0,0,0]},p))
    for n in (4,8,16,32,64):
        p=[length(),i('strchr',buf='a',off=0,char=0,out='p'),emit(),emit('$p')]
        cases.append(case('last_byte_terminator',['x'],{'a':['@x']+[1]*(n-2)+[0]},p))
        cases.append(case('allocation_without_terminator',['x'],{'a':['@x']+[1]*(n-1)},p))
    p=[length()]+[i('scalar',fn='add',left='$n',right=1,width=64,out='n') for _ in range(62)]+[emit()]
    cases.append(case('depth_boundary',['x'],{'a':['@x',0]},p))
    # These cases distinguish SAT from UNSAT, not merely emitted values.
    p=[i('store',buf='a',off=0,value=1),length(),i('scalar_eq',left='$n',right=2,out='g'),i('assume',value='$g'),emit(1)]
    cases.append(case('erasure_feasibility',['x'],{'a':[0,'@x',0]},p,[i('erase_tail',buf='a')]+p,'different'))
    p=[i('strchr',buf='a',off=0,char=0,out='n'),i('scalar_lt',left=-1,right='$n',out='g'),i('assume',value='$g'),emit(1)]
    q=copy.deepcopy(p);q[0]['op']='strchr_no_zero'
    cases.append(case('terminator_feasibility',['x','y'],{'a':['@x','@y',0]},p,q,'different'))
    guard=[i('byte_eq',left=read('a'),right=0,out='g'),i('assume',value='$g'),i('mask_eq',value=read('b'),mask=128,equal=128,out='g'),i('assume',value='$g')]
    p=guard+[i('strcmp',a='a',ao=0,b='b',bo=0,out='n'),i('scalar_lt',left='$n',right=0,out='g'),i('assume',value='$g'),emit(1)]
    q=copy.deepcopy(p);q[len(guard)]['op']='strcmp_signed'
    cases.append(case('signed_feasibility',['x','y'],{'a':['@x',0],'b':['@y',0]},p,q,'different'))
    p=[i('byte_eq',left=read('a'),right=0,out='z'),i('scalar_eq',left='$z',right=0,out='g'),i('assume',value='$g'),i('strlen_cached',buf='a',off=0,out='old'),i('store',buf='a',off=1,value=1),i('strlen_cached',buf='a',off=0,out='n'),i('scalar_eq',left='$n',right=2,out='g'),i('assume',value='$g'),emit(1)]
    q=copy.deepcopy(p);q[4]['op']='store_stale'
    cases.append(case('cache_feasibility',['x'],{'a':['@x',0,0]},p,q,'different'))
    for k,c in enumerate(cases,1):c['id']=f'C{k:03d}'
    return cases

def main(root:Path):
    root.mkdir(parents=True,exist_ok=True)
    for c in build():(root/(c['id']+'.json')).write_text(json.dumps(c,indent=2)+'\n')
if __name__=='__main__':main(Path(__file__).resolve().parents[1]/'cases')
