"""
Core of the deferred expression engine.
"""

from functools import wraps
from collections import Iterable
from numbers import Number, Integral

from ndtable.expr.nodes import Node

# conditional import of Numpy; if it doesn't exist, then set up dummy objects
# for the things we use
try:
    import numpy as np
except ImportError:
    np = {"integer": Integral}

#------------------------------------------------------------------------
# Globals
#------------------------------------------------------------------------

_max_argument_recursion = 25
_max_argument_len       = 1000
_argument_sample        = 100
_perform_typecheck      = False

def set_max_argument_len(val):
    global _max_argument_len
    _max_argument_len = val

def set_max_argument_recursion(val):
    global _max_argument_recursion
    _max_argument_recursion = val

#------------------------------------------------------------------------
# Method Maps
#------------------------------------------------------------------------

PyObject_BinaryOperators = [
    ('or','|'),  ('and','&'), ('xor','^'), ('lshift','<<'), ('rshift','>>'),
    ('add','+'), ('sub','-'), ('mul','*'), ('div','/'), ('mod','%'),
    ('truediv','/'), ('floordiv','//'), ('lt','<'), ('gt','>'), ('le','<='),
    ('ge','>='), ('eq','=='), ('ne','!=')
]

PyObject_UnaryOperators = [
    ('neg','-'), ('pos','+'), ('invert','~')
]

PyObject_Intrinsics = [
    'str', 'hash', 'abs', 'complex', 'int', 'long', 'float',
    'iter', 'oct', 'hex'
]

PyArray_Intrinsics = [
    "dtype", "size"
]

PyArray_WriteMethods = [
    'fill', 'itemset', 'put', 'setflags', 'setfield'
]

PyArray_ReadMethods = [
    'all', 'any', 'argmax', 'argmin', 'argsort', 'astype', 'base', 'byteswap',
    'choose', 'clip', 'compress', 'conj', 'conjugate', 'copy', 'ctypes',
    'cumprod', 'cumsum', 'data', 'diagonal', 'dot', 'dtype', 'dump', 'dumps',
    'flatten', 'getfield', 'item', 'max', 'mean', 'min', 'nbytes',
    'newbyteorder', 'nonzero', 'prod', 'ptp', 'ravel', 'repeat', 'reshape',
    'resize', 'round', 'searchsorted', 'setasflat', 'sort', 'squeeze', 'std',
    'sum', 'swapaxes', 'take', 'trace', 'transpose', 'var', 'view'
]

def lift_magic(f):
    @wraps(f)
    def fn(*args):
        iargs = injest_iterable(args)
        return f(*iargs)
    return fn

#------------------------------------------------------------------------
# Graph Construction
#------------------------------------------------------------------------

def is_homogeneous(it):
    # type() comparisions are cheap pointer arithmetic on
    # PyObject->tp_type, isinstance() calls are expensive since
    # they have travese the whole mro hierarchy

    head = it[0]
    head_type = type(head)
    return head, all(type(a) == head_type for a in it)

def injest_iterable(args, depth=0):
    # TODO: Should be 1 stack frame per each recursion so we
    # don't blow up Python trying to parse big structures

    if depth > _max_argument_recursion:
        raise RuntimeError(\
        "Maximum recursion depth reached while parsing arguments")

    # tuple, list, dictionary, any recursive combination of them
    if isinstance(args, Iterable):

        if len(args) == 0:
            return []

        if len(args) < _max_argument_len:
            sample = args[0:_argument_sample]

            # If the first 100 elements are type homogenous then
            # it's likely the rest of the iterable is.
            head, is_homog = is_homogeneous(sample)
            is_hetero = not is_homog


            # Homogenous Arguments
            # ====================

            if is_homog:
                if isinstance(head, Number):
                    return [ScalarNode(a) for a in args]
                elif isinstance(head, basestring):
                    return [StringNode(a) for a in args]
                elif isinstance(head, NDTable):
                    return [a for a in args]
                else:
                    return args

            # Heterogenous Arguments
            # ======================

            # TODO: This will be really really slow, certainly
            # not something we'd want to put in a loop.
            # Optimize later!

            elif is_hetero:
                ret = []
                for a in args:
                    if isinstance(a, (list, tuple)):
                        sub = injest_iterable(a, depth+1)
                        ret.append(sub)
                    elif isinstance(a, NDTable):
                        ret.append(a)
                    elif isinstance(a, Node):
                        ret.append(a)
                    elif isinstance(a, Number):
                        ret.append(ScalarNode(a))
                    elif isinstance(a, basestring):
                        ret.append(StringNode(a))
                    else:
                        raise TypeError("Unknown type")
                return ret

        else:
            raise RuntimeError("""
            "Too many dynamic arguments to build expression
            graph. Consider alternative construction.""")

#------------------------------------------------------------------------
# Base Classes
#------------------------------------------------------------------------

class ExpressionNode(Node):
    """
    A node which supports the full set of PyNumberMethods
    methods.
    """

    def eval(self):
        pass

    def generate_node(self, arity, fname, args=None, kwargs=None):

        # TODO: factor out circular imports
        from ndtable.expr.ops import functions

        # TODO: also kwargs when we support such things
        iargs = injest_iterable(args)

        #op = functions[fname]
        op = functions.get(fname, Op)

        # Make sure the graph makes sense given the signature of
        # the function. Does naive type checking.
        if _perform_typecheck:
            assert op.typecheck(args), "Does not typecheck"
        # Or just let it fail at runtime.
        else:
            pass


        if arity == 1:
            assert len(iargs) == arity
            return op(fname, iargs)

        if arity == 2:
            assert len(iargs) == arity
            return op(fname, iargs)

        elif arity == -1:
            return op(fname, iargs, kwargs)

    # Python Intrinsics
    # -----------------
    for name in PyObject_Intrinsics:
        # Bound methods are actually just unary functions with
        # the first argument self implicit
        exec (
            "def __%(name)s__(self):\n"
            "    return self.generate_node(1, '%(name)s', [self])"
            "\n"
        ) % locals()

    # Unary
    # -----
    for name, op in PyObject_UnaryOperators:
        exec (
            "def __%(name)s__(self):\n"
            "    return self.generate_node(1, '%(name)s', [self])"
            "\n"
        ) % locals()

    # Binary
    # ------
    for name, op in PyObject_BinaryOperators:
        exec (
            "def __%(name)s__(self, ob):\n"
            "    return self.generate_node(2, '%(name)s', [self, ob])\n"
            "\n"
            "def __r%(name)s__(self, ob):\n"
            "    return self.generate_node(2, '%(name)s', [self, ob])\n"
            "\n"
        )  % locals()

    for name, op in PyObject_BinaryOperators:
        exec (
            "def __i%(name)s__(self, ob):\n"
            "    return self.generate_node(2, '%(name)s', [self, ob])\n"
            "\n"
        )  % locals()



class ArrayNode(ExpressionNode):
    """
    A array structure with dimension and length.
    """

    # Read Operations
    # ===============

    for name in PyArray_ReadMethods:
        exec (
            "def %(name)s(self, *args, **kwargs):\n"
            "    args = (self,) + args\n"
            "    return self.generate_node(-1, '%(name)s', args, kwargs)"
            "\n"
        ) % locals()

    # Write Operations
    # ===============

    for name in PyArray_WriteMethods:
        exec (
            "def %(name)s(self, *args, **kwargs):\n"
            "    return self.generate_node(-1, '%(name)s', args, kwargs)\n"
            "\n"
        ) % locals()

    # Numpy-compatible shape/flag attributes
    # ======================================
    # These are evaluated in immediate mode, and do not return a deferred
    # graph node.  This implies that stream-generating functions (i.e. nodes
    # whose shape information requires a data evaluation) will actually
    # trigger an eval().

    @property
    def flags(self):
        pass

    @property
    def itemsize(self):
        pass

    @property
    def strides(self):
        pass

    @property
    def shape(self):
        pass

    @property
    def ndim(self):
        pass

    @property
    def size(self):
        pass

    @property
    def dtype(self):
        pass

    def __len__(self):
        # TODO: needs to query datashape
        pass

    # Numpy-compatible data attributes
    # ================================

    @property
    def imag(self):
        return Op('imag', self)

    @property
    def real(self):
        return Op('imag', self)

    @property
    def flat(self):
        """ Equivalent to .reshape(), which returns a graph node. """
        return Op('flat', self)

    @property
    def T(self):
        """ Equivalent to .transpose(), which returns a graph node. """
        return Op('transpose', self)

    # Read Operations
    # ===============

    def __getitem__(self, idx):
        """ Slicing operations should return graph nodes, while individual
        element access should return bare scalars.
        """
        if isinstance(idx, Integral) or isinstance(idx, np.integer):
            ndx = IndexNode((idx,))
            return Slice('getitem', [self, ndx])
        else:
            ndx = IndexNode(idx)
            return Slice('getitem', [self, ndx])

    def __getslice__(self, start, stop):
        """
        """
        ndx = IndexNode((start, stop))
        return Slice('getslice', [self, ndx])

    # Other non-graph methods
    # ========================

    def tofile(self, *args, **kw):
        pass

    def tolist(self, *args, **kw):
        pass

    def tostring(self, *args, **kw):
        pass


class Op(ExpressionNode):
    __slots__ = ['children', 'op']

    def __init__(self, op, operands):
        self.op = op
        self.children = operands

    @classmethod
    def typecheck(cls, operands):
        # TODO: unification

        if not hasattr(cls, 'signature'):
            return True

        tokens = [
            tok.strip()
            for tok in
            cls.signature.split('->')
        ]

        dom = tokens[0:-1]
        cod = tokens[-1]

        rigid  = [tokens.count(token)  > 1 for token in dom]
        free   = [tokens.count(token) == 1 for token in dom]

        assert len(dom) == cls.arity
        env = {}

        dom_vars = dom

        for i, (var, types, operand) in enumerate(zip(dom_vars, cls.dom, operands)):

            # Check if the type satisfies the kind constraint
            # -----------------------------------------------

            if free[i]:
                if type(operand) not in types:
                    return False

            if rigid[i]:
                if env.get(var):
                    if type(operand) != env.get(var):
                        return False

            # The value satifies the kind, now check that it is
            # in the space of allowable domain types.
            # --------------------------------------------------

                if type(operand) in types:
                    env[var] = type(operand)
                else:
                    return False

        # Type checks!
        return True

    @property
    def name(self):
        return self.op


class Slice(Op):
    # $0, start, stop, step
    arity = 4

#------------------------------------------------------------------------
# Table
#------------------------------------------------------------------------

# A thin wrapper around a Node object
class NDTable(ArrayNode):

    def __init__(self, args, depends=None):
        # We want the operations on the table to be
        # closed ( in the algebraic sense ) so that we don't
        # escape to Tables when we're using DataTables.
        if depends is None:
            self.children = injest_iterable(args)
        else:
            self.children = depends

    @property
    def name(self):
        return self.debug_name() # for now

    def debug_name(self):
        # unholy magic, just for debugging! Returns the variable
        # name of the object assigned to
        #
        #    a = NDTable()
        #    a.name == 'a'

        import sys, gc

        def find_names(obj):
            frame = sys._getframe(1)
            while frame is not None:
                frame.f_locals
                frame = frame.f_back

            for referrer in gc.get_referrers(obj):
                if isinstance(referrer, dict):
                    for k, v in referrer.iteritems():
                        if v is obj:
                            if len(k) == 1:
                                return k

        return find_names(self)

#------------------------------------------------------------------------
# Values
#------------------------------------------------------------------------

class Literal(Node):
    __slots__ = ['children', 'vtype']

    def __init__(self, val):
        assert isinstance(val, self.vtype)
        self.val = val
        self.children = []

    @property
    def name(self):
        return str(self.val)

class ScalarNode(Literal):
    vtype = int

class StringNode(Literal):
    vtype = str

class IndexNode(Literal):
    vtype = tuple

    @property
    def name(self):
        return 'Index%s' % str(self.val)
