"""Witness-Compiled Transactional Rollouts (WCTR), restricted Python containers.

New candidate operation: compile a witnessed mutation frontier into an eager
alias-closed fork, retain a write journal that deoptimizes unanticipated writes,
and graft the speculative output before restoring the parent state.
Copy-on-write, transactions, selective copying, and profiling are precedents,
not claimed as inventions. No program's environment dynamics are corrected.
"""
from __future__ import annotations
import ast,copy,operator,types,pickle
from collections import defaultdict
from contextvars import ContextVar

CURRENT=ContextVar('wctr_journal',default=None)
MUTATORS={'append','extend','insert','pop','remove','clear','update','setdefault',
          'add','discard','difference_update','intersection_update',
          'symmetric_difference_update','reverse','sort','popitem'}

def children(x):
    if isinstance(x,dict):return list(x.items())
    if isinstance(x,(list,tuple)):return list(enumerate(x))
    return []

def graph(root):
    nodes={};parents=defaultdict(set);paths={};stack=[(root,())]
    while stack:
        x,path=stack.pop()
        if not isinstance(x,(dict,list,set,tuple)):continue
        oid=id(x)
        if oid in nodes:continue
        nodes[oid]=x;paths[oid]=path
        for k,v in children(x):
            if isinstance(v,(dict,list,set,tuple)):
                parents[id(v)].add(oid);stack.append((v,path+(k,)))
    return nodes,parents,paths

def alias_fork(root,targets,pregraph=None,private_out=None):
    """Path-copy the reverse alias closure of targets; preserve other objects.

    Dict/list cycles are supported. Tuple cycles fall back to deepcopy, since
    tuple construction cannot fill a cycle incrementally in this implementation.
    """
    nodes,parents,paths=pregraph or graph(root)
    affected=set(targets)&nodes.keys();todo=list(affected)
    while todo:
        for p in parents[todo.pop()]:
            if p not in affected:affected.add(p);todo.append(p)
    memo={};active=set()
    def clone(x):
        oid=id(x)
        if oid not in affected:return x
        if oid in memo:return memo[oid]
        if isinstance(x,dict):
            out=defaultdict(x.default_factory) if isinstance(x,defaultdict) else {}
            memo[oid]=out
            for k,v in x.items():out[k]=clone(v)
        elif isinstance(x,list):
            out=[];memo[oid]=out;out.extend(clone(v) for v in x)
        elif isinstance(x,set):out=x.copy();memo[oid]=out
        else:
            if oid in active:raise ValueError('tuple cycle')
            active.add(oid);out=tuple(clone(v) for v in x);memo[oid]=out;active.remove(oid)
        if private_out is not None:private_out.add(id(out))
        return out
    try:return clone(root),len(memo)
    except ValueError:return copy.deepcopy(root),len(nodes)

def _record(obj):
    journal=CURRENT.get()
    if journal is not None:journal.record(obj)

def private(obj):
    journal=CURRENT.get()
    if journal is not None and isinstance(obj,(dict,list,set,tuple)):
        journal.private.add(id(obj))
    return obj

def write(value,obj,key):
    _record(obj);obj[key]=value

def delete(obj,key):
    _record(obj);del obj[key]

def mutate(obj,name,*args,**kwargs):
    _record(obj);return getattr(obj,name)(*args,**kwargs)

OPS={ast.Add:operator.iadd,ast.Sub:operator.isub,ast.Mult:operator.imul,
     ast.BitOr:operator.ior,ast.BitAnd:operator.iand}

def augment(obj,key,rhs,op):
    # Generated models use side-effect-free numeric RHSs for these updates.
    old=obj[key];value=rhs();_record(obj);_record(old);obj[key]=OPS[op](old,value)

class Instrument(ast.NodeTransformer):
    def allocation(self,node):
        return ast.copy_location(ast.Call(ast.Name('_wctr_private',ast.Load()),[node],[]),node)
    def visit_Dict(self,node):return self.allocation(self.generic_visit(node))
    def visit_List(self,node):
        node=self.generic_visit(node)
        return self.allocation(node) if isinstance(node.ctx,ast.Load) else node
    def visit_Set(self,node):return self.allocation(self.generic_visit(node))
    def visit_ListComp(self,node):return self.allocation(self.generic_visit(node))
    def visit_DictComp(self,node):return self.allocation(self.generic_visit(node))
    def visit_SetComp(self,node):return self.allocation(self.generic_visit(node))
    def visit_Assign(self,node):
        node=self.generic_visit(node)
        if len(node.targets)==1 and isinstance(node.targets[0],ast.Subscript):
            t=node.targets[0]
            return ast.copy_location(ast.Expr(ast.Call(ast.Name('_wctr_write',ast.Load()),
                [node.value,t.value,t.slice],[])),node)
        return node
    def visit_Delete(self,node):
        node=self.generic_visit(node)
        if all(isinstance(t,ast.Subscript) for t in node.targets):
            return [ast.copy_location(ast.Expr(ast.Call(ast.Name('_wctr_delete',ast.Load()),
                    [t.value,t.slice],[])),node) for t in node.targets]
        return node
    def visit_AugAssign(self,node):
        node=self.generic_visit(node)
        if isinstance(node.target,ast.Subscript) and type(node.op) in OPS:
            t=node.target
            args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[])
            return ast.copy_location(ast.Expr(ast.Call(ast.Name('_wctr_augment',ast.Load()),
                [t.value,t.slice,ast.Lambda(args,node.value),ast.Name(type(node.op).__name__,ast.Load())],[])),node)
        return node
    def visit_Call(self,node):
        node=self.generic_visit(node)
        if isinstance(node.func,ast.Attribute) and node.func.attr in MUTATORS:
            return ast.copy_location(ast.Call(ast.Name('_wctr_mutate',ast.Load()),
                [node.func.value,ast.Constant(node.func.attr)]+node.args,node.keywords),node)
        if ((isinstance(node.func,ast.Attribute) and node.func.attr=='copy') or
            (isinstance(node.func,ast.Name) and node.func.id in ['dict','list','set','defaultdict'])):
            return self.allocation(node)
        return node

def compile_source(source,filename):
    tree=Instrument().visit(ast.parse(source,filename));ast.fix_missing_locations(tree)
    env={'_wctr_write':write,'_wctr_delete':delete,'_wctr_mutate':mutate,'_wctr_private':private,
         '_wctr_augment':augment,**{k.__name__:k for k in OPS}}
    exec(compile(tree,filename,'exec'),env)
    return env

class Journal:
    def __init__(self,root,pregraph=None,private_ids=None):
        self.root=root;self.data=pregraph;self.saved={};self.private=private_ids or set()
    def ensure_graph(self):
        if self.data is None:self.data=graph(self.root)
        return self.data
    def record(self,obj):
        oid=id(obj)
        if oid in self.private:return
        nodes=self.ensure_graph()[0]
        if oid in nodes and oid not in self.saved:
            if isinstance(obj,(dict,list,set)):self.saved[oid]=(obj,obj.copy())
    def restore(self):
        for obj,snapshot in reversed(list(self.saved.values())):
            if isinstance(obj,dict):obj.clear();obj.update(snapshot)
            elif isinstance(obj,list):obj[:]=snapshot
            else:obj.clear();obj.update(snapshot)

def signature(action):return str(action).strip().split(' ',1)[0].lower()

def pattern(path):return tuple('*' if isinstance(k,int) else k for k in path)

def match_targets(root,patterns,action):
    result=set()
    for path,selector in patterns:
        states=[root]
        for key in path:
            nxt=[]
            for obj in states:
                if key=='*':
                    if isinstance(obj,(list,tuple)):nxt.extend(obj)
                    elif isinstance(obj,dict):nxt.extend(obj.values())
                elif isinstance(obj,dict) and key in obj:nxt.append(obj[key])
            states=nxt
        for obj in states:
            if selector is not None:
                if not isinstance(obj,dict) or not str(action).endswith(str(obj.get(selector,'\0'))):continue
            result.add(id(obj))
    return result

class Adapter:
    def __init__(self,model,method='wctr'):
        self.model=model;self.method=method
        self.frontiers=defaultdict(set);self.top_fields=defaultdict(set)
        self.calls=0;self.copied=0;self.deopts=0;self.sites=0
        self.full_clones=0
        self.cache={}
        initial=model.init_belief() if hasattr(model,'init_belief') else {}
        self.dd_fallback=any(isinstance(x,defaultdict) for x in graph(initial)[0].values())
    def remember(self,root,action,nodes,paths,dirty):
        for oid in dirty:
            path=paths.get(oid)
            if path is None:continue
            obj=nodes[oid];selector=None
            if isinstance(obj,dict) and path and isinstance(path[-1],int):
                candidates=[k for k,v in obj.items() if isinstance(v,str) and v
                            and str(action).endswith(v)]
                if candidates:selector=min(candidates,key=lambda k:(-len(str(obj[k])),str(k)))
            self.frontiers[signature(action)].add((pattern(path),selector))
            self.top_fields[signature(action)].add(path[0] if path else None)
    def transition(self,state,action):
        self.calls+=1
        if self.method=='raw':return self.model.predict_belief(state,action)
        if self.method=='deepcopy':
            self.full_clones+=1
            return self.model.predict_belief(copy.deepcopy(state),action)
        if self.method=='memo_deepcopy':
            key=(pickle.dumps(state,protocol=5),action)
            if key in self.cache:return copy.deepcopy(self.cache[key])
            self.full_clones+=1
            output=self.model.predict_belief(copy.deepcopy(state),action)
            self.cache[key]=copy.deepcopy(output)
            return output
        # defaultdict reads can insert entries without an explicit Python write
        # site. Preserve semantics with the ordinary strong fallback.
        if self.dd_fallback:
            self.full_clones+=1
            underlying=getattr(self.model,'_wctr_raw_model',self.model)
            return underlying.predict_belief(copy.deepcopy(state),action)
        inputs=state
        pregraph=None;private_ids=set()
        if self.method=='wctr':
            target=match_targets(state,self.frontiers[signature(action)],action)
            if target:
                pregraph=graph(state)
                inputs,n=alias_fork(state,target,pregraph,private_ids);self.copied+=n
        elif self.method=='topfield':
            target=set()
            for k in self.top_fields[signature(action)]:
                obj=state if k is None else state.get(k)
                if isinstance(obj,(dict,list,set,tuple)):target.update(graph(obj)[0])
            if target:
                pregraph=graph(state)
                inputs,n=alias_fork(state,target,pregraph,private_ids);self.copied+=n
        # Journal only original input objects; eagerly forked objects are private.
        journal=Journal(state,pregraph,private_ids);token=CURRENT.set(journal)
        try:
            output=self.model.predict_belief(inputs,action)
            if journal.saved:
                self.deopts+=1;self.sites+=len(journal.saved)
                nodes,parents,paths=journal.ensure_graph()
                self.remember(state,action,nodes,paths,journal.saved)
                output,n=alias_fork(output,set(journal.saved));self.copied+=n
            return output
        finally:
            journal.restore();CURRENT.reset(token)

    def calibrate(self,cases):
        # All adapters see the same finite calibration states/actions. Labels are
        # unnecessary for the transaction method; no environment query is made.
        for state,action in cases:
            saved=copy.deepcopy(state)
            self.transition(saved,action)
        self.calls=self.copied=self.deopts=self.sites=0
        self.full_clones=0
