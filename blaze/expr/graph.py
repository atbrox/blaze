"""
Holds the base classes for graph nodes.
"""

from uuid import uuid4
from numbers import Integral
from collections import Iterable

from blaze.expr import nodes, catalog
from blaze.datashape import coretypes
from blaze.sources.canonical import PythonSource
from blaze.datashape.coretypes import int_, float_, string, top, dynamic

# Type checking and unification
from blaze.datashape.unification import unify
from blaze.expr.typechecker import tyeval, typesystem

# conditional import of Numpy; if it doesn't exist, then set up dummy objects
# for the things we use
try:
    import numpy as np
except ImportError:
    np = {"integer": Integral}

#------------------------------------------------------------------------
# Globals
#------------------------------------------------------------------------

OP  = 0 # OP/FUN??
APP = 1
VAL = 2

_max_argument_recursion = 25
_max_argument_len       = 1000
_argument_sample        = 100

def set_max_argument_len(val):
    global _max_argument_len
    _max_argument_len = val

def set_max_argument_recursion(val):
    global _max_argument_recursion
    _max_argument_recursion = val

#------------------------------------------------------------------------
# Exceptions
#------------------------------------------------------------------------

class UnknownExpression(Exception):
    def __init__(self, obj):
        self.obj = obj
    def __str__(self):
        return 'Unknown object in expression: %r' % (self.obj,)

class DeferredDatashape(Exception):
    def __str__(self):
        return 'Datashape deferred until eval()'

#------------------------------------------------------------------------
# Deconstructors
#------------------------------------------------------------------------


def typeof(obj):
    """
    BlazeT value deconstructor, maps values to types. Only
    defined for Blaze types.

    >>> typeof(IntNode(3))
    int64
    >>> typeof(Any())
    top
    >>> typeof(NDArray([1,2,3]))
    dshape("3, int64")
    """
    typ = type(obj)

    # -- special case --
    if isinstance(obj, ArrayNode):
        return obj.datashape

    if typ is App:
        return obj.cod
    elif typ is IntNode:
        return int_
    elif typ is FloatNode:
        return float_
    elif typ is StringNode:
        return string
    elif typ is dynamic:
        return top
    else:
        raise UnknownExpression(obj)

def all_simple(operands):
    """ Determine if all the operands are simple numeric types """
    simple_types = set([IntNode, FloatNode])
    return all(type(op) in simple_types for op in operands)

#------------------------------------------------------------------------
# Blaze Typesystem
#------------------------------------------------------------------------

# unify   : the type unification function
# top     : the top type
# dynamic : the dynamic type
# typeof  : the value deconstructor

# Judgements over a type system are uniquely defined by three things:
#
# * a type unifier
# * a top type
# * a value deconstructor
# * universe of first order terms

BlazeT = typesystem(unify, top, any, typeof)

#------------------------------------------------------------------------
# Graph Construction
#------------------------------------------------------------------------

def is_homogeneous(it):
    # type() comparisions are cheap pointer arithmetic on
    # PyObject->tp_type, isinstance() calls are expensive since
    # they have travese the whole mro hierarchy

    # Checks Python types for arguments, not to be confused with the
    # datashape types and the operator types!

    head = it[0]
    head_type = type(head)
    return head, all(type(a) == head_type for a in it)

def injest_iterable(args, depth=0, force_homog=False):
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

            if force_homog and not is_homog:
                raise TypeError("Input is not homogenous.")

            # Homogenous Arguments
            # ====================

            if is_homog:
                if isinstance(head, int):
                    return [IntNode(a) for a in args]
                if isinstance(head, float):
                    return [FloatNode(a) for a in args]
                elif isinstance(head, basestring):
                    return [StringNode(a) for a in args]
                elif isinstance(head, ArrayNode):
                    return [a for a in args]
                else:
                    return args

            # Heterogenous Arguments
            # ======================

            # TODO: This will be really really slow, certainly
            # not something we'd want to put in a loop.
            # Optimize later!

            elif not is_homog:
                ret = []
                for a in args:
                    if isinstance(a, (list, tuple)):
                        sub = injest_iterable(a, depth+1)
                        ret.append(sub)
                    elif isinstance(a, ArrayNode):
                        ret.append(a)
                    elif isinstance(a, basestring):
                        ret.append(StringNode(a))
                    elif isinstance(a, int):
                        ret.append(IntNode(a))
                    elif isinstance(a, float):
                        ret.append(FloatNode(a))
                    elif isinstance(a, nodes.Node):
                        ret.append(a)
                    else:
                        raise TypeError("Unknown type")
                return ret

        else:
            raise RuntimeError("""
            Too many dynamic arguments to build expression
            graph. Consider alternative construction.""")

#------------------------------------------------------------------------
# Base Classes
#------------------------------------------------------------------------

class ExpressionNode(nodes.Node):
    """
    A abstract node which supports the full set of PyNumberMethods
    methods.
    """
    abstract = True

    def generate_opnode(self, arity, func_name, args=None, kwargs=None):

        # TODO: also kwargs when we support such things
        iargs = injest_iterable(args)

        # Lookup by capitalized name
        op = Op._registry[func_name.capitalize()]

        if arity == 1:
            iop = op(func_name, iargs)
            return App(iop)

        if arity == 2:
            iop = op(func_name, iargs)
            return App(iop)

        elif arity == -1:
            return op(func_name, iargs, kwargs)

    def generate_fnnode(self, fname, args=None, kwargs=None):
        pass

    # Python Intrinsics
    # -----------------
    for name in catalog.PyObject_Intrinsics:
        # Bound methods are actually just unary functions with
        # the first argument self implicit
        exec (
            "def __%(name)s__(self):\n"
            "    return self.generate_opnode(1, '%(name)s', [self])"
            "\n"
        ) % locals()
        del name

    # Unary
    # -----
    for name, _ in catalog.PyObject_UnaryOperators:
        exec (
            "def __%(name)s__(self):\n"
            "    return self.generate_opnode(1, '%(name)s', [self])"
            "\n"
        ) % locals()
        del name
        del _

    # Binary
    # ------
    for name, _ in catalog.PyObject_BinaryOperators:
        exec (
            "def __%(name)s__(self, ob):\n"
            "    return self.generate_opnode(2, '%(name)s', [self, ob])\n"
            "\n"
            "def __r%(name)s__(self, ob):\n"
            "    return self.generate_opnode(2, '%(name)s', [self, ob])\n"
            "\n"
        )  % locals()
        del name
        del _

    for name, _ in catalog.PyObject_BinaryOperators:
        exec (
            "def __i%(name)s__(self, ob):\n"
            "    return self.generate_opnode(2, '%(name)s', [self, ob])\n"
            "\n"
        )  % locals()
        del name
        del _

#------------------------------------------------------------------------
# Indexables
#------------------------------------------------------------------------

class ArrayNode(ExpressionNode):
    """
    A array structure with dimension and length.
    """
    kind = VAL

    # Read Operations
    # ===============

    for name in catalog.PyArray_ReadMethods:
        exec (
            "def %(name)s(self, *args, **kwargs):\n"
            "    args = (self,) + args\n"
            "    return self.generate_opnode(-1, '%(name)s', args, kwargs)"
            "\n"
        ) % locals()
        del name

    # Write Operations
    # ===============

    for name in catalog.PyArray_WriteMethods:
        exec (
            "def %(name)s(self, *args, **kwargs):\n"
            "    return self.generate_opnode(-1, '%(name)s', args, kwargs)\n"
            "\n"
        ) % locals()
        del name

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
        if isinstance(idx, slice):
            ndx = IndexNode((idx.start, idx.stop, idx.step))
            return Slice('getitem', [self, ndx])
        elif isinstance(idx, Integral) or isinstance(idx, np.integer):
            ndx = IndexNode((idx,))
            return Slice('getitem', [self, ndx])
        else:
            ndx = IndexNode(idx)
            return Slice('getitem', [self, ndx])

    # Other non-graph methods
    # ========================

    def tofile(self, *args, **kw):
        pass

    def tolist(self, *args, **kw):
        pass

    def tostring(self, *args, **kw):
        pass

#------------------------------------------------------------------------
# Application
#------------------------------------------------------------------------

class App(ExpressionNode):
    """
    The application of an operand producing concrete values.

    For example:

        In[0]: a = 2 + 3

    The resulting value of ``a`` is App( Op(+), 2, 3).

    """
    __slots__ = ['itype','otype']
    kind = APP

    def __init__(self, operator):
        self.operator = operator
        self.children = [operator]

        self.datashape = operator.datashape

    @property
    def dom(self):
        """ Domain """
        return self.operator.dom

    @property
    def cod(self):
        """ Codomain """
        return self.operator.cod

    @property
    def name(self):
        return 'App'

#------------------------------------------------------------------------
# Function Call
#------------------------------------------------------------------------

class FunApp(ExpressionNode):
    """
    Function application.
    """

    __slots__ = ['itype','otype']
    kind = APP

    def __init__(self, function):
        self.function = function
        self.children = [function]

        self.nin  = len(function.dom)
        self.nout = len(function.cod)

    @property
    def dom(self):
        """ Domain """
        return self.operator.dom

    @property
    def cod(self):
        """ Codomain """
        return self.operator.cod

    @property
    def name(self):
        return 'FunApp'

#------------------------------------------------------------------------
# Op
#------------------------------------------------------------------------

class NamedOp(type):
    """
    Metaclass to track Op subclasses.
    """

    def __init__(cls, name, bases, dct):
        abstract = dct.pop('abstract', False)
        if not hasattr(cls, '_registry'):
            cls._registry = {}

        if not abstract:
            cls._registry[name] = cls

        super(NamedOp, cls).__init__(name, bases, dct)

class Op(ExpressionNode):
    """
    A typed operator taking a set of typed operands.
    """

    __slots__ = ['children', 'op', 'cod']
    __metaclass__ = NamedOp
    kind = OP

    def __init__(self, op, operands):
        self.op = op
        self.children = operands
        self.operands = operands
        self._opaque = False

        # If all the operands to the expression are simple
        # numeric types then go ahead and determine what the
        # datashape of this operator is before we hit eval().

        # Examples:
        #    IntNode, IntNode
        #    IntNode, FloatNode

        # minor hack until we get graph level numbering of
        # expression objects
        self.uuid = str(uuid4())

        # Make sure the graph makes sense given the signature of
        # the function. Does naive type checking and inference.

    @property
    def nin(self):
        raise NotImplementedError

    @property
    def nout(self):
        raise NotImplementedError

    @property
    def opaque(self):
        """
        We don't know anything about the operator, no types, no argument
        signature ... we just throw things into and things pop out or it
        blows up.
        """
        return self._opaque or (not hasattr(self, 'signature'))

    @property
    def datashape(self):
        """ If possible determine the datashape before we even
        hit eval(). This is possible for simple types.
        """
        if all_simple(self.operands) and self.is_arithmetic:
            return coretypes.promote(*self.operands)
        else:
            return dynamic

#------------------------------------------------------------------------
# Functions
#------------------------------------------------------------------------

class NamedFun(type):
    """
    Metaclass to track Fun subclasses.
    """

    def __init__(cls, name, bases, dct):
        abstract = dct.pop('abstract', False)
        if not hasattr(cls, '_registry'):
            cls._registry = {}

        if not abstract:
            cls._registry[name] = cls

        super(NamedFun, cls).__init__(name, bases, dct)

class Fun(ExpressionNode):
    """
    """
    __slots__ = ['children', 'fn', 'cod']
    __metaclass__ = NamedFun

    def __init__(self, fn, arguments):
        self.fn = fn
        self.children = arguments

#------------------------------------------------------------------------
# Values
#------------------------------------------------------------------------

class Literal(ExpressionNode):
    __slots__ = ['children', 'vtype']
    kind      = VAL

    def __init__(self, val):
        assert isinstance(val, self.vtype)
        self.val = val
        self.children = []
        self.datashape = coretypes.from_python_scalar(val)

    @property
    def name(self):
        return str(self.val)

    @property
    def data(self):
        raise NotImplementedError

#------------------------------------------------------------------------
# Strings
#------------------------------------------------------------------------

class StringNode(Literal):
    vtype     = str
    datashape = string
    kind      = VAL

    datashape = coretypes.string

    @property
    def data(self):
        return PythonSource(self.val, type=str)

#------------------------------------------------------------------------
# Scalars
#------------------------------------------------------------------------

class IntNode(Literal):
    vtype     = int
    datashape = int_
    kind      = VAL

    datashape = coretypes.int_

    @property
    def data(self):
        return PythonSource(self.val, type=int)

class FloatNode(Literal):
    vtype     = float
    datashape = float_
    kind      = VAL

    datashape = coretypes.double

    @property
    def data(self):
        return PythonSource(self.val, type=float)

#------------------------------------------------------------------------
# Slices and Indexes
#------------------------------------------------------------------------

class IndexNode(Literal):
    arity  = 4 # <INDEXABLE>, <INDEXER>
    vtype = tuple
    kind  = OP

    @property
    def name(self):
        return 'Index%s' % str(self.val)

class Slice(Op):
    arity  = 4 # <INDEXABLE>, start, stop, step
    opaque = True
    kind   = OP
