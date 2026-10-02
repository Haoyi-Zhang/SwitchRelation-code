"""Certificate producer for an owned, bounded C-string operational fragment.

No solver, target executable, or network access. Byte data may only be copied,
compared, or tested by declared unary masks. Scalar bitvectors are separate.
"""
from __future__ import annotations
import itertools, json, math
from pathlib import Path
from typing import Any, Iterator

SCHEMAS = {
 'strlen': {'op','buf','off','out'}, 'strlen_cached': {'op','buf','off','out'},
 'strlen_capacity': {'op','buf','off','out'},
 'strchr': {'op','buf','off','char','out'},
 'strchr_no_zero': {'op','buf','off','char','out'},
 'strcmp': {'op','a','ao','b','bo','out'},
 'strcmp_signed': {'op','a','ao','b','bo','out'},
 'store': {'op','buf','off','value'}, 'store_stale': {'op','buf','off','value'},
 'memmove': {'op','dst','do','src','so','n'},
 'move_forward': {'op','dst','do','src','so','n'},
 'strcpy': {'op','dst','do','src','so'},
 'copy_no_zero': {'op','dst','do','src','so'},
 'strcat': {'op','dst','do','src','so'},
 'switch': {'op','buf'}, 'erase_tail': {'op','buf'},
 'mask_eq': {'op','value','mask','equal','out'},
 'byte_eq': {'op','left','right','out'},
 'byte_lt': {'op','left','right','out'},
 'scalar': {'op','fn','left','right','width','out'},
 'scalar_eq': {'op','left','right','out'},
 'scalar_lt': {'op','left','right','out'},
 'const': {'op','value','out'}, 'assume': {'op','value'},
 'emit': {'op','value'},
}
class Rejected(ValueError): pass
class Fault(Exception): pass

def validate(case: dict[str, Any], max_variables: int = 32) -> tuple[list[int],list[tuple[int,int]],bool]:
    if set(case) != {'id','family','variables','buffers','reference','candidate','expected'}:
        raise Rejected('case fields')
    if any(not isinstance(case[k],str) or not case[k].isascii() or not case[k].isidentifier() or len(case[k])>64 for k in ('id','family')):
        raise Rejected('case metadata')
    vs=case['variables']; bufs=case['buffers']
    if not isinstance(vs,list) or len(vs)>max_variables or len(set(vs))!=len(vs) or any(not isinstance(v,str) or not v.isidentifier() for v in vs):
        raise Rejected('variables')
    if not isinstance(bufs,dict) or not 1<=len(bufs)<=4: raise Rejected('buffers')
    constants={0}; masks=[]; signed=False
    def byte(x):
        if type(x) is int and 0<=x<256: constants.add(x); return
        if isinstance(x,dict) and set(x)=={'read'} and isinstance(x['read'],list) and len(x['read'])==2:
            b,o=x['read']; buffer(b); scalar(o);return
        raise Rejected('byte expression')
    def buffer(b):
        if b not in bufs: raise Rejected('buffer reference')
    regs=set()
    def scalar(x):
        if type(x) is int and -(1<<64)<=x<1<<64:return
        if isinstance(x,str) and x.startswith('$') and x[1:] in regs:return
        raise Rejected('scalar expression or register scope')
    for b,a in bufs.items():
        if not isinstance(b,str) or not isinstance(a,list) or not 1<=len(a)<=64:raise Rejected('allocation')
        for x in a:
            if x is None:continue
            if type(x) is int and 0<=x<256: constants.add(x)
            elif isinstance(x,str) and x.startswith('@') and x[1:] in vs:pass
            else:raise Rejected('initial byte')
    used={x[1:] for a in bufs.values() for x in a if isinstance(x,str)}
    if used != set(vs):raise Rejected('unused or missing variable')
    for key in ['reference','candidate']:
        prog=case[key];regs=set()
        if not isinstance(prog,list) or not 1<=len(prog)<=64:raise Rejected('path length')
        if sum(isinstance(a,dict) and a.get('op') in ('assume','mask_eq','byte_eq','byte_lt','scalar_eq','scalar_lt') for a in prog)>48:raise Rejected('predicate count')
        for a in prog:
            if not isinstance(a,dict) or a.get('op') not in SCHEMAS or set(a)!=SCHEMAS[a['op']]:raise Rejected('unsupported syntax')
            op=a['op']
            for fld in ('buf','a','b','dst','src'):
                if fld in a:buffer(a[fld])
            for fld in ('off','ao','bo','do','so','n'):
                if fld in a:scalar(a[fld])
            if op.startswith('strchr'):byte(a['char'])
            if op.startswith('store'):byte(a['value'])
            if op=='mask_eq':
                byte(a['value'])
                if type(a['mask']) is not int or type(a['equal']) is not int or not 0<=a['mask']<256 or not 0<=a['equal']<256:raise Rejected('mask')
                masks.append((a['mask'],a['equal']))
            if op in ('byte_eq','byte_lt'):byte(a['left']);byte(a['right'])
            if op=='strcmp_signed':signed=True
            if op in ('scalar','scalar_eq','scalar_lt'):
                scalar(a['left']);scalar(a['right'])
                if op=='scalar' and (a['fn'] not in ('add','sub','and','or','xor','shl','lshr') or type(a['width']) is not int or not 1<=a['width']<=64):raise Rejected('scalar operator')
            if op in ('assume','emit','const'):scalar(a['value'])
            if 'out' in a:
                if not isinstance(a['out'],str) or not a['out'].isidentifier():raise Rejected('output register')
                regs.add(a['out'])
    if case['expected'] not in ('equivalent','different'):raise Rejected('expectation')
    return sorted(constants),sorted(set(masks)),signed

def partition(case: dict[str, Any]) -> list[list[int]]:
    constants,masks,signed=validate(case);cs=set(constants)
    def sig(x):return (x if x in cs else -1,tuple((x&m)==k for m,k in masks), x>=128 if signed else False)
    cells=[];lo=0;prev=sig(0)
    for x in range(1,256):
        s=sig(x)
        if s!=prev:cells.append([lo,x-1]);lo=x;prev=s
    cells.append([lo,255]);return cells

def assignments(cells: list[list[int]],m: int) -> Iterator[tuple[int,...]]:
    p=[x for lo,hi in cells for x in range(lo,min(hi+1,lo+m))]
    if len(p)**m>1_000_000:raise Rejected('enumeration admission bound')
    for xs in itertools.product(p,repeat=m):
        if all((not (u:=sorted(set(x for x in xs if lo<=x<=hi)))) or u==list(range(lo,lo+len(u))) for lo,hi in cells):yield xs

def weight(cells: list[list[int]],xs: tuple[int,...]) -> int:
    return math.prod(math.comb(hi-lo+1,len(set(x for x in xs if lo<=x<=hi))) for lo,hi in cells)

def count_representatives(cells: list[list[int]],m: int)->int:
    # Product of exponential generating functions for ordered set partitions.
    stir=[[0]*(m+1) for _ in range(m+1)];stir[0][0]=1
    for n in range(1,m+1):
        for k in range(1,n+1):stir[n][k]=stir[n-1][k-1]+k*stir[n-1][k]
    dp=[1]+[0]*m
    for lo,hi in cells:
        f=[sum(math.factorial(k)*stir[n][k] for k in range(min(n,hi-lo+1)+1)) for n in range(m+1)]
        dp=[sum(math.comb(n,j)*dp[n-j]*f[j] for j in range(n+1)) for n in range(m+1)]
    return dp[m]

class Machine:
    def __init__(self,case,values,strings=False):
        env=dict(zip(case['variables'],values));self.strings=strings;self.reg={};self.cache={};self.emits=[]
        raw={b:[env[x[1:]] if isinstance(x,str) else x for x in a] for b,a in case['buffers'].items()}
        self.init={b:[v is not None for v in a] for b,a in raw.items()}
        self.mem={b:(''.join(chr(v or 0) for v in a) if strings else [v or 0 for v in a]) for b,a in raw.items()}
    def num(self,x):return self.reg[x[1:]] if isinstance(x,str) else x
    def bounds(self,b,o,n=1):
        if o<0 or n<0 or o+n>len(self.mem[b]):raise Fault('bounds')
    def read(self,b,o):
        self.bounds(b,o)
        if not self.init[b][o]:raise Fault('uninitialized')
        v=self.mem[b][o];return ord(v) if self.strings else v
    def byte(self,x):return self.read(x['read'][0],self.num(x['read'][1])) if isinstance(x,dict) else x
    def put(self,b,o,vals,stale=False):
        self.bounds(b,o,len(vals))
        if self.strings:self.mem[b]=self.mem[b][:o]+''.join(map(chr,vals))+self.mem[b][o+len(vals):]
        else:self.mem[b][o:o+len(vals)]=vals
        self.init[b][o:o+len(vals)]=[True]*len(vals)
        if not stale:self.cache={k:v for k,v in self.cache.items() if k[0]!=b}
    def end(self,b,o):
        self.bounds(b,o)
        if self.strings:
            e=self.mem[b].find(chr(0),o)
            upto=len(self.mem[b]) if e<0 else e+1
            for j in range(o,upto):self.read(b,j)
            if e<0:raise Fault('unterminated')
            return e
        for j in range(o,len(self.mem[b])):
            if self.read(b,j)==0:return j
        raise Fault('unterminated')
    def overlap(self,d,do,dn,s,so,sn):
        if d==s and max(do,so)<min(do+dn,so+sn):raise Fault('overlap')
    def run(self,prog):
        try:
            for a in prog:
                op=a['op'];r=None
                if op in ('strlen','strlen_cached','strlen_capacity'):
                    b,o=a['buf'],self.num(a['off']);k=(b,o)
                    if op=='strlen_cached' and k in self.cache:r=self.cache[k]
                    else:
                        try:r=self.end(b,o)-o
                        except Fault as e:
                            if op=='strlen_capacity' and str(e)=='unterminated':r=len(self.mem[b])-o
                            else:raise
                        if op=='strlen_cached':self.cache[k]=r
                elif op in ('strchr','strchr_no_zero'):
                    b,o,c=a['buf'],self.num(a['off']),self.byte(a['char']);e=self.end(b,o)
                    stop=e if op=='strchr_no_zero' else e+1
                    if self.strings:r=self.mem[b].find(chr(c),o,stop)
                    else:r=next((i for i in range(o,stop) if self.read(b,i)==c),-1)
                    if r>=0:r-=o
                elif op in ('strcmp','strcmp_signed'):
                    b,o,c,p=a['a'],self.num(a['ao']),a['b'],self.num(a['bo']);e=self.end(b,o);f=self.end(c,p)
                    if self.strings and op=='strcmp':
                        s,t=self.mem[b][o:e],self.mem[c][p:f];r=int(s>t)-int(s<t)
                    else:
                        r=0
                        for j in range(min(e-o,f-p)+1):
                            u,v=self.read(b,o+j),self.read(c,p+j)
                            if op=='strcmp_signed':u=u if u<128 else u-256;v=v if v<128 else v-256
                            if u!=v:r=int(u>v)-int(u<v);break
                            if u==0:break
                elif op in ('store','store_stale'):
                    self.put(a['buf'],self.num(a['off']),[self.byte(a['value'])],op=='store_stale')
                elif op in ('memmove','move_forward'):
                    d,s,o,p,n=a['dst'],a['src'],self.num(a['do']),self.num(a['so']),self.num(a['n'])
                    self.bounds(s,p,n);self.bounds(d,o,n)
                    vals=[self.read(s,p+j) for j in range(n)]
                    if op=='move_forward':
                        for j in range(n):self.put(d,o+j,[self.read(s,p+j)])
                    else:self.put(d,o,vals)
                elif op in ('strcpy','copy_no_zero','strcat'):
                    d,s,o,p=a['dst'],a['src'],self.num(a['do']),self.num(a['so']);e=self.end(s,p);n=e-p+1
                    start=o
                    if op=='strcat':start=self.end(d,o)
                    self.bounds(d,start,n);self.overlap(d,o,start-o+n,s,p,n)
                    vals=[self.read(s,p+j) for j in range(n-(op=='copy_no_zero'))]
                    self.put(d,start,vals)
                elif op=='switch':
                    # The string backend already stores the complete allocation.
                    pass
                elif op=='erase_tail':
                    b=a['buf'];e=self.end(b,0)
                    for j in range(e+1,len(self.mem[b])):
                        if self.init[b][j]:self.put(b,j,[0])
                elif op=='mask_eq':r=int((self.byte(a['value'])&a['mask'])==a['equal'])
                elif op in ('byte_eq','byte_lt'):
                    u,v=self.byte(a['left']),self.byte(a['right']);r=int(u==v) if op=='byte_eq' else int(u<v)
                elif op in ('scalar_eq','scalar_lt'):
                    u,v=self.num(a['left']),self.num(a['right']);r=int(u==v) if op=='scalar_eq' else int(u<v)
                elif op=='scalar':
                    w=a['width'];mask=(1<<w)-1;u=self.num(a['left'])&mask;v=self.num(a['right'])&mask
                    f=a['fn']
                    if f=='add':r=(u+v)&mask
                    elif f=='sub':r=(u-v)&mask
                    elif f=='and':r=u&v
                    elif f=='or':r=u|v
                    elif f=='xor':r=u^v
                    elif f=='shl':r=0 if v>=w else (u<<v)&mask
                    else:r=0 if v>=w else u>>v
                elif op=='const':r=self.num(a['value'])
                elif op=='assume':
                    if not self.num(a['value']):return ['reject',self.emits]
                elif op=='emit':self.emits.append(self.num(a['value']))
                else:raise Rejected('unknown operation')
                if 'out' in a:self.reg[a['out']]=r
            return ['accept',self.emits]
        except Fault as e:return ['fault',str(e),self.emits]

def certify(case,max_rows=30000):
    cells=partition(case);m=len(case['variables']);count=count_representatives(cells,m)
    if count>max_rows:raise Rejected('canonical obligation budget')
    rows=[];mismatch=None;acceptance_witness=None;counts={'reference_accept':0,'candidate_accept':0,'reference_fault':0,'candidate_fault':0,'different':0,'acceptance_different':0}
    for xs in assignments(cells,m):
        left=Machine(case,xs).run(case['reference']);right=Machine(case,xs,True).run(case['candidate']);w=weight(cells,xs)
        rows.append([list(xs),w,left,right])
        for side,val in [('reference',left),('candidate',right)]:
            if val[0]=='accept':counts[side+'_accept']+=w
            if val[0]=='fault':counts[side+'_fault']+=w
        if (left[0]=='accept') != (right[0]=='accept'):
            counts['acceptance_different']+=w
            if acceptance_witness is None:acceptance_witness=list(xs)
        if left!=right:
            counts['different']+=w
            if mismatch is None:mismatch=list(xs)
    if len(rows) != count:
        raise Rejected('canonical representative count mismatch')
    return {'statement':case,'cells':cells,'rows':rows,'verdict':'different' if mismatch is not None else 'equivalent','least_input':mismatch,'full_domain':256**m,'weighted_counts':counts,'feasibility':{'reference':'sat' if counts['reference_accept'] else 'unsat','candidate':'sat' if counts['candidate_accept'] else 'unsat','verdict':'same_inputs' if acceptance_witness is None else 'different_inputs','least_input':acceptance_witness}}
