"""Standalone finite certificate replayer. Does not import the producer.

Coverage is checked by disjoint canonical rows and exact combinatorial weights,
not by trusting a producer's enumeration count. This is not a proof assistant.
"""
from __future__ import annotations
import json, math
from pathlib import Path
from typing import Any

class Invalid(ValueError): pass
class BadState(Exception): pass

def require(ok: bool,msg: str)->None:
    if not ok:raise Invalid(msg)

FIELDS={
 'strlen':'buf off out','strlen_cached':'buf off out','strlen_capacity':'buf off out',
 'strchr':'buf off char out','strchr_no_zero':'buf off char out',
 'strcmp':'a ao b bo out','strcmp_signed':'a ao b bo out',
 'store':'buf off value','store_stale':'buf off value',
 'memmove':'dst do src so n','move_forward':'dst do src so n',
 'strcpy':'dst do src so','copy_no_zero':'dst do src so','strcat':'dst do src so',
 'switch':'buf','erase_tail':'buf','mask_eq':'value mask equal out',
 'byte_eq':'left right out','byte_lt':'left right out',
 'scalar':'fn left right width out','scalar_eq':'left right out','scalar_lt':'left right out',
 'const':'value out','assume':'value','emit':'value',
}

def inspect_statement(c, max_variables=32):
    require(isinstance(c,dict) and set(c)==set('id family variables buffers reference candidate expected'.split()),'statement fields')
    require(all(isinstance(c[k],str) and c[k].isascii() and c[k].isidentifier() and len(c[k])<=64 for k in ('id','family')),'case metadata')
    v=c['variables'];b=c['buffers']
    require(isinstance(v,list) and len(v)<=max_variables and all(isinstance(x,str) and x.isidentifier() for x in v),'variable list')
    require(len(v)==len(set(v)),'duplicate variable')
    require(isinstance(b,dict) and 1<=len(b)<=4,'buffer count')
    fixed={0};tests=[];signed=False;used=set()
    for name,buf in b.items():
        require(isinstance(name,str) and isinstance(buf,list) and 1<=len(buf)<=64,'buffer declaration')
        for value in buf:
            if value is None:continue
            if type(value) is int and 0<=value<=255:fixed.add(value)
            else:
                require(isinstance(value,str) and value.startswith('@') and value[1:] in v,'initial value')
                used.add(value[1:])
    require(used==set(v),'input variable coverage')
    for seqname in ('reference','candidate'):
        seq=c[seqname];known=set()
        require(isinstance(seq,list) and 0<len(seq)<=64,'instruction count')
        require(sum(isinstance(a,dict) and a.get('op') in ('assume','mask_eq','byte_eq','byte_lt','scalar_eq','scalar_lt') for a in seq)<=48,'predicate count')
        def integer(x):
            require((type(x) is int and -(2**64)<=x<2**64) or (isinstance(x,str) and x.startswith('$') and x[1:] in known),'scalar typing')
        def datum(x):
            if type(x) is int:
                require(0<=x<=255,'byte literal');fixed.add(x)
            else:
                require(isinstance(x,dict) and set(x)=={'read'} and isinstance(x['read'],list) and len(x['read'])==2,'byte typing')
                name,index=x['read'];require(name in b,'read allocation');integer(index)
        for ins in seq:
            require(isinstance(ins,dict) and ins.get('op') in FIELDS,'unknown instruction')
            op=ins['op'];require(set(ins)==set(FIELDS[op].split())|{'op'},'instruction fields')
            for k in ('buf','a','b','src','dst'):
                if k in ins:require(ins[k] in b,'allocation operand')
            for k in ('off','ao','bo','so','do','n'):
                if k in ins:integer(ins[k])
            if op in ('store','store_stale'):datum(ins['value'])
            if op in ('strchr','strchr_no_zero'):datum(ins['char'])
            if op in ('byte_eq','byte_lt'):datum(ins['left']);datum(ins['right'])
            if op=='mask_eq':
                datum(ins['value'])
                require(all(type(ins[k]) is int and 0<=ins[k]<=255 for k in ('mask','equal')),'unary mask')
                tests.append((ins['mask'],ins['equal']))
            if op=='strcmp_signed':signed=True
            if op in ('scalar','scalar_eq','scalar_lt'):
                integer(ins['left']);integer(ins['right'])
                if op=='scalar':
                    require(ins['fn'] in ('add','sub','and','or','xor','shl','lshr'),'scalar function')
                    require(type(ins['width']) is int and 1<=ins['width']<=64,'scalar width')
            if op in ('const','assume','emit'):integer(ins['value'])
            if 'out' in ins:
                require(isinstance(ins['out'],str) and ins['out'].isidentifier(),'register name');known.add(ins['out'])
    require(c['expected'] in ('equivalent','different'),'expectation label')
    # A boundary must be introduced whenever adjacent bytes are distinguishable.
    def distinguish(x,y):
        if x in fixed or y in fixed:return True
        if signed and (x<128)!=(y<128):return True
        return any(((x&m)==k)!=((y&m)==k) for m,k in tests)
    endpoints=[0]+[i for i in range(1,256) if distinguish(i-1,i)]+[256]
    return [[endpoints[i],endpoints[i+1]-1] for i in range(len(endpoints)-1)]

def interpret(case,values,program):
    """Direct list-and-scan semantics, separate from the string producer."""
    variables=dict(zip(case['variables'],values))
    heap={k:[variables[v[1:]] if isinstance(v,str) else v for v in a] for k,a in case['buffers'].items()}
    regs={};saved={};seen=[]
    def integer(v):return regs[v[1:]] if isinstance(v,str) else v
    def span(name,start,size):
        if not (0<=start and 0<=size and start+size<=len(heap[name])):raise BadState('bounds')
    def load(name,index):
        span(name,index,1);val=heap[name][index]
        if val is None:raise BadState('uninitialized')
        return val
    def data(v):return load(v['read'][0],integer(v['read'][1])) if isinstance(v,dict) else v
    def term(name,start):
        span(name,start,1);i=start
        while i<len(heap[name]):
            if load(name,i)==0:return i
            i+=1
        raise BadState('unterminated')
    def write(name,start,values,clear=True):
        span(name,start,len(values))
        for j,v in enumerate(values):heap[name][start+j]=v
        if clear:
            for k in list(saved):
                if k[0]==name:del saved[k]
    try:
        for ins in program:
            op=ins['op'];result=None
            if op in ('strlen','strlen_cached','strlen_capacity'):
                name=ins['buf'];start=integer(ins['off']);key=(name,start)
                if op=='strlen_cached' and key in saved:result=saved[key]
                else:
                    try:result=term(name,start)-start
                    except BadState as e:
                        if op!='strlen_capacity' or str(e)!='unterminated':raise
                        result=len(heap[name])-start
                    if op=='strlen_cached':saved[key]=result
            elif op in ('strchr','strchr_no_zero'):
                name=ins['buf'];start=integer(ins['off']);needle=data(ins['char']);end=term(name,start);result=-1
                for i in range(start,end+int(op=='strchr')):
                    if load(name,i)==needle:result=i-start;break
            elif op in ('strcmp','strcmp_signed'):
                x,y=ins['a'],ins['b'];i,j=integer(ins['ao']),integer(ins['bo'])
                term(x,i);term(y,j);result=0
                while True:
                    u,v=load(x,i),load(y,j)
                    if op=='strcmp_signed':
                        if u>=128:u-=256
                        if v>=128:v-=256
                    if u<v:result=-1;break
                    if u>v:result=1;break
                    if u==0:break
                    i+=1;j+=1
            elif op in ('store','store_stale'):
                name=ins['buf'];start=integer(ins['off']);value=data(ins['value'])
                write(name,start,[value],op!='store_stale')
            elif op in ('memmove','move_forward'):
                s,d=ins['src'],ins['dst'];i,j,n=integer(ins['so']),integer(ins['do']),integer(ins['n'])
                span(s,i,n);span(d,j,n);original=[load(s,i+k) for k in range(n)]
                if op=='memmove':write(d,j,original)
                else:
                    for k in range(n):write(d,j+k,[load(s,i+k)])
            elif op in ('strcpy','copy_no_zero','strcat'):
                s,d=ins['src'],ins['dst'];i,j=integer(ins['so']),integer(ins['do']);end=term(s,i);n=end-i+1
                where=term(d,j) if op=='strcat' else j
                span(d,where,n)
                if s==d:
                    readset=set(range(i,i+n));destset=set(range(j,where+n))
                    if readset&destset:raise BadState('overlap')
                new=[load(s,k) for k in range(i,end+1)]
                if op=='copy_no_zero':new=new[:-1]
                write(d,where,new)
            elif op=='switch':pass
            elif op=='erase_tail':
                name=ins['buf'];end=term(name,0)
                for i in range(end+1,len(heap[name])):
                    if heap[name][i] is not None:write(name,i,[0])
            elif op=='mask_eq':result=int(data(ins['value']) & ins['mask']==ins['equal'])
            elif op=='byte_eq':result=int(data(ins['left'])==data(ins['right']))
            elif op=='byte_lt':result=int(data(ins['left'])<data(ins['right']))
            elif op=='scalar_eq':result=int(integer(ins['left'])==integer(ins['right']))
            elif op=='scalar_lt':result=int(integer(ins['left'])<integer(ins['right']))
            elif op=='scalar':
                modulus=2**ins['width'];u=integer(ins['left'])%modulus;v=integer(ins['right'])%modulus
                name=ins['fn']
                if name=='add':result=(u+v)%modulus
                elif name=='sub':result=(u-v)%modulus
                elif name=='and':result=u&v
                elif name=='or':result=u|v
                elif name=='xor':result=u^v
                elif name=='shl':result=0 if v>=ins['width'] else (u*2**v)%modulus
                else:result=0 if v>=ins['width'] else u//2**v
            elif op=='const':result=integer(ins['value'])
            elif op=='assume':
                if integer(ins['value'])==0:return ['reject',seen]
            elif op=='emit':seen.append(integer(ins['value']))
            else:raise Invalid('interpreter opcode')
            if 'out' in ins:regs[ins['out']]=result
        return ['accept',seen]
    except BadState as e:return ['fault',str(e),seen]

def exact_json(value):
    """This certificate language has integer numbers, not floats or booleans."""
    if value is None or type(value) in (int, str):
        return
    if type(value) is list:
        for item in value: exact_json(item)
        return
    if type(value) is dict:
        require(all(type(k) is str for k in value), 'JSON object key type')
        for item in value.values(): exact_json(item)
        return
    raise Invalid('unsupported JSON value type')

def check(case: dict[str,Any],certificate: dict[str,Any])->dict[str,Any]:
    exact_json(case); exact_json(certificate)
    require(isinstance(certificate,dict) and set(certificate)==set('statement cells rows verdict least_input full_domain weighted_counts feasibility'.split()),'certificate fields')
    require(certificate['statement']==case,'statement binding')
    cells=inspect_statement(case);require(cells==certificate['cells'],'partition mismatch')
    rows=certificate['rows'];require(isinstance(rows,list) and 1<=len(rows)<=30000,'row count bound')
    m=len(case['variables']);total=0;previous=None;least=None;acceptance_witness=None
    counts={k:0 for k in ('reference_accept','candidate_accept','reference_fault','candidate_fault','different','acceptance_different')}
    for row in rows:
        require(isinstance(row,list) and len(row)==4,'row structure');values,w,left,right=row
        require(isinstance(values,list) and len(values)==m and all(type(x) is int and 0<=x<256 for x in values),'input row')
        require(previous is None or tuple(previous)<tuple(values),'duplicate or unordered row');previous=values
        w_expected=1
        for lo,hi in cells:
            distinct=sorted({x for x in values if lo<=x<=hi})
            require(distinct==[lo+i for i in range(len(distinct))],'noncanonical row')
            # Number of strictly increasing selections for this ordered pattern.
            w_expected*=math.comb(hi-lo+1,len(distinct))
        require(type(w) is int and w==w_expected,'class weight')
        require(left==interpret(case,values,case['reference']),'reference evaluation')
        require(right==interpret(case,values,case['candidate']),'candidate evaluation')
        total+=w
        for side,out in (('reference',left),('candidate',right)):
            if out[0]=='accept':counts[side+'_accept']+=w
            if out[0]=='fault':counts[side+'_fault']+=w
        if (left[0]=='accept') != (right[0]=='accept'):
            counts['acceptance_different']+=w
            if acceptance_witness is None:acceptance_witness=values
        if left!=right:
            counts['different']+=w
            if least is None:least=values
    require(total==256**m and certificate['full_domain']==total,'incomplete domain cover')
    verdict='equivalent' if least is None else 'different'
    require(certificate['verdict']==verdict,'verdict')
    require(certificate['least_input']==least,'least witness')
    require(certificate['weighted_counts']==counts,'weighted results')
    feasibility={'reference':'sat' if counts['reference_accept'] else 'unsat','candidate':'sat' if counts['candidate_accept'] else 'unsat','verdict':'same_inputs' if acceptance_witness is None else 'different_inputs','least_input':acceptance_witness}
    require(certificate['feasibility']==feasibility,'feasibility summary')
    return {'id':case['id'],'verdict':verdict,'rows':len(rows),'full_domain':total,'least_input':least,'weighted_counts':counts,'feasibility':feasibility}

def load(path: Path):
    require(path.stat().st_size<=64*1024*1024,'input file size')
    def unique(pairs):
        d={}
        for k,v in pairs:
            require(k not in d,'duplicate JSON key');d[k]=v
        return d
    def bad_constant(text):
        raise Invalid('non-finite JSON number')
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique,parse_constant=bad_constant)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('case',type=Path);p.add_argument('certificate',type=Path);a=p.parse_args()
    try:print(json.dumps(check(load(a.case),load(a.certificate)),sort_keys=True))
    except (Invalid,KeyError,TypeError,ValueError,RecursionError,OSError) as e:raise SystemExit('REJECT: '+str(e))
