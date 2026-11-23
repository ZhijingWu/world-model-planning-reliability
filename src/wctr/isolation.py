"""Witness-Compiled Transactional Rollouts (WCTR), restricted Python containers.

New candidate operation: compile a witnessed mutation frontier into an eager
alias-closed fork, retain a write journal that deoptimizes unanticipated writes,
and graft the speculative output before restoring the parent state.
Copy-on-write, transactions, selective copying, and profiling are precedents,
not claimed as inventions. No program's environment dynamics are corrected.
"""
from __future__ import annotations
import ast,builtins,copy,symtable,types,pickle
from collections import defaultdict
from contextvars import ContextVar
from functools import partial

CURRENT=ContextVar('wctr_journal',default=None)
MUTATORS={'append','extend','insert','pop','remove','clear','update','setdefault',
          'add','discard','difference_update','intersection_update',
          'symmetric_difference_update','reverse','sort','popitem'}

_PLAIN_CONTAINERS = (dict, list, tuple)
_GRAPH_CONTAINERS = (dict, list, tuple, set)
_SCALAR_TYPES = (type(None), bool, int, float, complex, str, bytes)


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
    if stop_on_fallback and type(root) not in _PLAIN_CONTAINERS + _SCALAR_TYPES:
        return None
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
            if stop_on_fallback and type(key) not in _SCALAR_TYPES:
                return None
            if isinstance(child, _GRAPH_CONTAINERS):
                parents[id(child)].add(oid)
                stack.append((child, path + (key,)))
            elif stop_on_fallback and type(child) not in _SCALAR_TYPES:
                return None
    return nodes, parents, paths


def _needs_full_copy(root):
    """Check the live input without allocating reverse edges or witness paths."""
    seen = set()
    stack = [root]
    while stack:
        obj = stack.pop()
        kind = type(obj)
        if kind not in _PLAIN_CONTAINERS:
            if kind not in _SCALAR_TYPES:
                return True
            continue
        oid = id(obj)
        if oid not in seen:
            seen.add(oid)
            if kind is dict:
                if any(type(k) not in _SCALAR_TYPES for k in obj):
                    return True
                stack.extend(obj.values())
            else:
                stack.extend(obj)
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

class _SubscriptTarget:
    """Used only as the base of a store/delete target, never as its value."""
    def __init__(self, obj):
        self.obj = obj

    def __getitem__(self, key):
        # AugAssign fetches the old value before evaluating its RHS. A native
        # in-place opcode can mutate that value even if the final store fails.
        old = self.obj[key]
        if isinstance(old, (dict, list, set)):
            _record(old)
        return old

    def __setitem__(self, key, value):
        _record(self.obj)
        self.obj[key] = value

    def __delitem__(self, key):
        _record(self.obj)
        del self.obj[key]


def _target(obj):
    return obj if CURRENT.get() is None else _SubscriptTarget(obj)

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


_PLAIN_CALLS = (len, isinstance, list, dict, tuple, set, str, int, float, bool,
                range, enumerate, zip, staticmethod, types.SimpleNamespace,
                ValueError, TypeError, LookupError, KeyError, IndexError,
                RuntimeError, AssertionError, Exception)
_READ_METHODS = {'copy', 'get', 'keys', 'values', 'items', 'endswith', 'startswith',
                 'count', 'index'}
# These runtime-owned keys cannot be supplied by a Python identifier or import.
_CODE_KEY = object()
_CLASSES_KEY = object()


def _compiled_function(func):
    if type(func) is types.MethodType:
        func = func.__func__
    return (type(func) is types.FunctionType
            and func.__code__ in func.__globals__.get(_CODE_KEY, ()))


def _checked_callable(func, mutator_site):
    journal = CURRENT.get()
    if journal is None:
        return func
    kind = type(func)
    native_method = kind in (types.BuiltinMethodType, types.MethodDescriptorType)
    named_method = native_method or kind in (types.MethodType, types.FunctionType)
    if mutator_site or (named_method and func.__name__ in MUTATORS):
        # Capture, descriptor binding and equality use the actual Python object.
        # The barrier applies at invocation, including for calls via local aliases.
        return partial(mutate, func)
    if native_method and func.__name__ in _READ_METHODS:
        owner = type(func.__self__) if kind is types.BuiltinMethodType else func.__objclass__
        if owner in (dict, list, tuple, str):
            return func
    if _compiled_function(func) or any(func is known for known in _PLAIN_CALLS):
        return func
    if kind is type and func in journal.classes:
        return func
    if not callable(func):
        return func  # Python evaluates the arguments and raises its usual TypeError.
    journal.reject("WCTR cannot certify this callable or mutator receiver")


def _model_method_value(value):
    journal = CURRENT.get()
    if journal is not None and callable(value):
        journal.reject("WCTR cannot expose this custom mutator receiver as a callback")
    return value


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

class Instrument(ast.NodeTransformer):
    def __init__(self, custom_captures):
        self.custom_captures = custom_captures

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
            check = ast.Call(ast.Name('wctr:pattern', ast.Load()), [subject], [])
            node.subject = ast.copy_location(check, subject)
        return node

    def allocation(self,node):
        return ast.copy_location(ast.Call(ast.Name('wctr:private',ast.Load()),[node],[]),node)
    def visit_Dict(self,node):return self.allocation(self.generic_visit(node))
    def visit_List(self,node):
        node=self.generic_visit(node)
        return self.allocation(node) if isinstance(node.ctx,ast.Load) else node
    def visit_Set(self,node):return self.allocation(self.generic_visit(node))
    def visit_ListComp(self,node):return self.allocation(self.generic_visit(node))
    def visit_DictComp(self,node):return self.allocation(self.generic_visit(node))
    def visit_SetComp(self,node):return self.allocation(self.generic_visit(node))
    def visit_Subscript(self, node):
        node = self.generic_visit(node)
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            base = node.value
            node.value = ast.copy_location(ast.Call(ast.Name('wctr:target', ast.Load()), [base], []), base)
        return node

    def visit_Call(self, node):
        node = self.generic_visit(node)
        func = node.func
        mutator_site = isinstance(func, ast.Attribute) and func.attr in MUTATORS
        node.func = ast.copy_location(ast.Call(ast.Name('wctr:call', ast.Load()),
                                               [func, ast.Constant(mutator_site)], []), func)
        return node

    def visit_Attribute(self, node):
        node = self.generic_visit(node)
        if node in self.custom_captures:
            return ast.copy_location(ast.Call(ast.Name('wctr:model-method', ast.Load()), [node], []), node)
        return node


# A new Python node takes native Full Copy until its effects have been reviewed.
_SELECTIVE_NODES = (
    ast.Module, ast.ClassDef, ast.FunctionDef, ast.arguments, ast.arg, ast.Return,
    ast.Assign, ast.AugAssign, ast.Delete, ast.NamedExpr, ast.For, ast.While,
    ast.If, ast.IfExp, ast.Try, ast.ExceptHandler, ast.Raise, ast.Pass, ast.Break,
    ast.Continue, ast.Expr, ast.Call, ast.keyword, ast.Attribute, ast.Subscript,
    ast.Slice, ast.Starred, ast.Name, ast.Constant, ast.Dict, ast.List, ast.Tuple,
    ast.Set, ast.ListComp, ast.SetComp, ast.DictComp, ast.comprehension, ast.BoolOp,
    ast.BinOp, ast.UnaryOp, ast.Compare, ast.Match, ast.match_case, ast.pattern,
    ast.expr_context, ast.operator, ast.unaryop, ast.boolop, ast.cmpop,
    ast.ImportFrom, ast.alias,
)
_BUILTIN_NAMES = frozenset(dir(builtins))
_SAFE_NAMES = {func.__name__ for func in _PLAIN_CALLS}
_EXCEPTION_NAMES = {cls.__name__ for cls in _PLAIN_CALLS
                    if type(cls) is type and issubclass(cls, BaseException)}


def _shadows_exception(table, names):
    if any(symbol.get_name() in names and
           (symbol.is_assigned() or symbol.is_parameter() or symbol.is_imported())
           for symbol in table.get_symbols()):
        return True
    return any(_shadows_exception(child, names) for child in table.get_children())


def _selective_source(tree, source, filename, custom_captures):
    methods = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    receiver_names = set()
    for cls in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
        for method in (item for item in cls.body if isinstance(item, ast.FunctionDef)):
            args = method.args.posonlyargs + method.args.args
            if args:
                receiver_names.add(args[0].arg)
    callees = {node.func for node in ast.walk(tree) if isinstance(node, ast.Call)}
    pattern_names = {part for node in ast.walk(tree) if isinstance(node, ast.match_case)
                     for part in ast.walk(node.pattern)}
    attributes = MUTATORS | _READ_METHODS | methods
    raised = set()
    for node in ast.walk(tree):
        if not isinstance(node, _SELECTIVE_NODES):
            return False
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module != 'types' or any(a.name != 'SimpleNamespace' for a in node.names):
                return False
        elif isinstance(node, ast.Name):
            if node.id.startswith('__') or (node.id in _BUILTIN_NAMES and node.id not in _SAFE_NAMES):
                return False
        elif isinstance(node, ast.ClassDef):
            if node.bases or node.keywords or node.decorator_list:
                return False
        elif isinstance(node, ast.FunctionDef):
            if node.decorator_list or node.name.startswith('__'):
                return False
        elif isinstance(node, ast.Attribute):
            if (not isinstance(node.ctx, ast.Load) or node.attr.startswith('__')
                    or node.attr not in attributes):
                return False
            if node not in callees and node not in pattern_names:
                # Native consumers can invoke an escaped callable without an
                # ast.Call (sort keys, mapping.keys, unpacking, ...).
                if (node.attr in methods and node.attr in MUTATORS
                        and isinstance(node.value, ast.Name) and node.value.id in receiver_names):
                    custom_captures.add(node)
                else:
                    return False
        elif isinstance(node, ast.MatchClass) and any(k not in MUTATORS for k in node.kwd_attrs):
            return False
        elif isinstance(node, ast.AugAssign):
            if not isinstance(node.target, ast.Subscript):
                return False
        elif isinstance(node, ast.comprehension) and node.is_async:
            return False
        elif isinstance(node, ast.keyword) and node.arg is None:
            return False
        elif isinstance(node, ast.Raise):
            # A mutable exception payload would otherwise be restored under the exception.
            exc = node.exc
            if (not isinstance(exc, ast.Call) or not isinstance(exc.func, ast.Name)
                    or exc.func.id not in _EXCEPTION_NAMES or exc.keywords or node.cause
                    or any(not isinstance(arg, ast.Constant) for arg in exc.args)):
                return False
            raised.add(exc.func.id)
    return not raised or not _shadows_exception(symtable.symtable(source, filename, 'exec'), raised)


def _code_objects(code):
    yield code
    for const in code.co_consts:
        if type(const) is types.CodeType:
            yield from _code_objects(const)


def compile_source(source, filename):
    tree = ast.parse(source, filename)
    env = {}
    custom_captures = set()
    if not _selective_source(tree, source, filename, custom_captures):
        exec(compile(tree, filename, 'exec', dont_inherit=True), env)
        return env
    tree = ast.fix_missing_locations(Instrument(custom_captures).visit(tree))
    code = compile(tree, filename, 'exec', dont_inherit=True)
    # Colons are illegal in Python identifiers. Source bindings cannot name a
    # helper. Star imports and dynamic namespace access select original code.
    env.update({'wctr:target': _target, 'wctr:call': _checked_callable,
                'wctr:private': private, 'wctr:pattern': _check_pattern_subject,
                'wctr:model-method': _model_method_value,
                _CODE_KEY: frozenset(_code_objects(code))})
    exec(code, env)
    env[_CLASSES_KEY] = frozenset(obj for obj in env.values() if type(obj) is type
                                  and obj.__module__ == env.get('__name__', 'builtins'))
    return env

class Journal:
    def __init__(self,root,pregraph=None,private_ids=None,classes=()):
        self.root=root;self.data=pregraph;self.saved={};self.private=private_ids or set()
        self.classes = classes
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

    def _reference_transition(self, state, action):
        model = getattr(self.model, '_wctr_raw_model', self.model)
        token = CURRENT.set(None)
        try:
            return model.predict_belief(self._full_copy(state), action)
        finally:
            CURRENT.reset(token)

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
        predict = self.model.predict_belief
        if (not _compiled_function(predict) or type(action) not in _SCALAR_TYPES
                or type(self.model) not in predict.__globals__[_CLASSES_KEY]
                or (self.method == 'topfield' and type(state) is not dict)):
            return self._reference_transition(state, action)
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
            return self._reference_transition(state, action)
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
        journal=Journal(state,pregraph,private_ids,predict.__globals__[_CLASSES_KEY]);token=CURRENT.set(journal)
        try:
            output=predict(inputs,action)
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
            try:
                journal.restore()
            finally:
                CURRENT.reset(token)

    def calibrate(self,cases):
        # All adapters see the same finite calibration states/actions. Labels are
        # unnecessary for the transaction method; no environment query is made.
        for state,action in cases:
            saved=copy.deepcopy(state)
            self.transition(saved,action)
        self.calls=self.copied=self.deopts=self.sites=0
        self.full_clones=0
