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
from functools import partial

CURRENT=ContextVar('wctr_journal',default=None)
MUTATORS={'append','extend','insert','pop','remove','clear','update','setdefault',
          'add','discard','difference_update','intersection_update',
          'symmetric_difference_update','reverse','sort','popitem'}

_PLAIN_CONTAINERS = (dict, list, tuple)
_GRAPH_CONTAINERS = (dict, list, tuple, set)


def _child_items(obj):
    if isinstance(obj, dict):
        return obj.items()
    if isinstance(obj, (list, tuple)):
        return enumerate(obj)
    return ()


def children(x):
    return list(_child_items(x))


def graph(root, *, stop_on_fallback=False):
    """Index all reverse edges and one witness path per container, in DFS order."""
    nodes, parents, paths = {}, defaultdict(set), {}
    stack = [(root, ())] if isinstance(root, _GRAPH_CONTAINERS) else []
    while stack:
        obj, path = stack.pop()
        oid = id(obj)
        if oid in nodes:
            continue
        if stop_on_fallback and type(obj) not in _PLAIN_CONTAINERS:
            return None
        nodes[oid] = obj
        paths[oid] = path
        for key, child in _child_items(obj):
            if isinstance(child, _GRAPH_CONTAINERS):
                parents[id(child)].add(oid)
                stack.append((child, path + (key,)))
    return nodes, parents, paths


def _needs_full_copy(root):
    """Check the live input without allocating reverse edges or witness paths."""
    seen = set()
    stack = [root]
    while stack:
        obj = stack.pop()
        kind = type(obj)
        if kind not in _PLAIN_CONTAINERS:
            if isinstance(obj, _GRAPH_CONTAINERS):
                return True  # Includes sets, defaultdicts and container subclasses.
            continue
        oid = id(obj)
        if oid not in seen:
            seen.add(oid)
            stack.extend(obj.values() if kind is dict else obj)
    return False

class _TupleCycle(Exception):
    """A tuple was revisited before its copy could be constructed."""


def alias_fork(root,targets,pregraph=None,private_out=None,*,full_copy=copy.deepcopy):
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
            if oid in active:raise _TupleCycle
            active.add(oid);out=tuple(clone(v) for v in x);memo[oid]=out;active.remove(oid)
        if private_out is not None:private_out.add(id(out))
        return out
    try:return clone(root),len(memo)
    except _TupleCycle:return full_copy(root),len(nodes)

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

def mutate(method, /, *args, **kwargs):
    journal = CURRENT.get()
    if journal is not None:
        if type(method) is types.MethodDescriptorType and method.__objclass__ in (list, dict, set):
            # list.append(xs, value) writes to xs, even if list has a different name.
            if not args or not issubclass(type(args[0]), method.__objclass__):
                # A native argument error cannot mutate state and may be caught by the model.
                return method(*args, **kwargs)
            receiver = args[0]
        elif type(method) is types.BuiltinMethodType:
            receiver = method.__self__
        else:
            journal.reject("WCTR cannot track the receiver of this mutator")
        if type(receiver) not in (list, dict, set, defaultdict):
            journal.reject("WCTR mutators require a built-in container receiver")
        journal.record(receiver)
    return method(*args, **kwargs)


class _GuardedMutator(partial):
    def __get__(self, instance, owner=None):
        # A callback captured in a class body retains the original descriptor binding.
        method = self.args[0]
        get = getattr(type(method), '__get__', None)
        if get is None:
            return self
        bound = get(method, instance, owner)
        return self if bound is method else bind_mutator(bound)


def bind_mutator(method):
    if type(method) is _GuardedMutator or not callable(method):
        return method
    return _GuardedMutator(mutate, method)


def _check_pattern_subject(subject):
    journal = CURRENT.get()
    if journal is not None:
        journal.reject("WCTR cannot track a mutator captured implicitly by a class pattern")
    return subject


def _captures_mutator(pattern):
    for node in ast.walk(pattern):
        if isinstance(node, ast.MatchClass):
            for attr, subpattern in zip(node.kwd_attrs, node.kwd_patterns):
                if attr in MUTATORS and any(
                    isinstance(part, ast.MatchAs) and part.name is not None
                    for part in ast.walk(subpattern)
                ):
                    return True
    return False

OPS={ast.Add:operator.iadd,ast.Sub:operator.isub,ast.Mult:operator.imul,
     ast.BitOr:operator.ior,ast.BitAnd:operator.iand}

def augment(obj,key,rhs,op):
    # Generated models use side-effect-free numeric RHSs for these updates.
    old=obj[key];value=rhs();_record(obj);_record(old);obj[key]=OPS[op](old,value)

class Instrument(ast.NodeTransformer):
    def visit(self, node):
        # Pattern attributes are dotted names in Python's grammar. The enclosing
        # match subject, case guards and case statements are ordinary executable nodes.
        if isinstance(node, ast.pattern):
            return node
        return super().visit(node)

    def visit_Match(self, node):
        node = self.generic_visit(node)
        if any(_captures_mutator(case.pattern) for case in node.cases):
            # Python can bind names during a partially failed pattern. Guard
            # before any pattern runs so a raw method cannot escape into a local.
            subject = node.subject
            check = ast.Call(ast.Name('_wctr_check_pattern_subject', ast.Load()), [subject], [])
            node.subject = ast.copy_location(check, subject)
        return node

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
    def visit_Attribute(self,node):
        node=self.generic_visit(node)
        if isinstance(node.ctx, ast.Load) and node.attr in MUTATORS:
            return ast.copy_location(ast.Call(ast.Name('_wctr_bind_mutator', ast.Load()), [node], []), node)
        return node

def compile_source(source,filename):
    tree=Instrument().visit(ast.parse(source,filename));ast.fix_missing_locations(tree)
    env={'_wctr_write':write,'_wctr_delete':delete,'_wctr_bind_mutator':bind_mutator,'_wctr_private':private,
         '_wctr_check_pattern_subject':_check_pattern_subject,
         '_wctr_augment':augment,**{k.__name__:k for k in OPS}}
    exec(compile(tree,filename,'exec'),env)
    return env

class Journal:
    def __init__(self,root,pregraph=None,private_ids=None):
        self.root=root;self.data=pregraph;self.saved={};self.private=private_ids or set()
        self.rejection = None
    def reject(self, reason):
        if self.rejection is None:
            self.rejection = reason
        raise TypeError(reason)
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

    def _full_copy(self, state):
        result = copy.deepcopy(state)
        self.full_clones += 1
        return result

    def transition(self,state,action):
        self.calls+=1
        if self.method=='raw':return self.model.predict_belief(state,action)
        if self.method=='deepcopy':
            return self.model.predict_belief(self._full_copy(state),action)
        if self.method=='memo_deepcopy':
            key=(pickle.dumps(state,protocol=5),action)
            if key in self.cache:return copy.deepcopy(self.cache[key])
            output=self.model.predict_belief(self._full_copy(state),action)
            self.cache[key]=copy.deepcopy(output)
            return output
        # A set's pop/iteration order can change on deepcopy; defaultdict reads can
        # insert keys. Choose the reference route before the model makes any writes.
        witnesses = ()
        if self.method == 'wctr':
            witnesses = self.frontiers[signature(action)]
        elif self.method == 'topfield':
            witnesses = self.top_fields[signature(action)]

        pregraph = None
        fallback = self.dd_fallback
        if not fallback:
            if witnesses:
                pregraph = graph(state, stop_on_fallback=True)
                fallback = pregraph is None
            else:
                # Journal.record builds the index before the first parent write.
                fallback = _needs_full_copy(state)
        if fallback:
            underlying=getattr(self.model,'_wctr_raw_model',self.model)
            return underlying.predict_belief(self._full_copy(state),action)
        inputs=state
        private_ids=set()
        if self.method=='wctr' and witnesses:
            target=match_targets(state,witnesses,action)
            if target:
                inputs,n=alias_fork(state,target,pregraph,private_ids,full_copy=self._full_copy);self.copied+=n
        elif self.method=='topfield' and witnesses:
            target=set()
            for k in witnesses:
                obj=state if k is None else state.get(k)
                if isinstance(obj,(dict,list,set,tuple)):target.update(graph(obj)[0])
            if target:
                inputs,n=alias_fork(state,target,pregraph,private_ids,full_copy=self._full_copy);self.copied+=n
        # Journal only original input objects; eagerly forked objects are private.
        journal=Journal(state,pregraph,private_ids);token=CURRENT.set(journal)
        try:
            output=self.model.predict_belief(inputs,action)
            # Model code may catch TypeError; it cannot turn an unsupported call
            # into a successful speculative transition or an online witness.
            if journal.rejection is not None:
                raise TypeError(journal.rejection)
            if journal.saved:
                self.deopts+=1;self.sites+=len(journal.saved)
                nodes,parents,paths=journal.ensure_graph()
                self.remember(state,action,nodes,paths,journal.saved)
                output,n=alias_fork(output,set(journal.saved),full_copy=self._full_copy);self.copied+=n
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
