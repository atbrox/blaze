"""
This defines the DataShape "type system".
"""

import ctypes
from numpy import dtype
from string import letters
from itertools import count, izip
from platform import architecture
from numbers import Integral
from operator import methodcaller, eq
from collections import Mapping, Sequence
from utils import ReverseLookupDict

free_vars = methodcaller('free')

def _var_generator():
    """
    Generate a stream of unique free variables.
    """
    for a in count(0):
        for b in letters:
            if a == 0:
                yield b
            else:
                yield ''.join([str(a),str(b)])

var_generator = _var_generator()

def expr_string(spine, const_args, outer=None):
    if not outer:
        outer = '()'

    if const_args:
        return str(spine) + outer[0] + ','.join(map(str,const_args)) + outer[1]
    else:
        return str(spine)

def shape_coerce(ob):
    if type(ob) is int:
        return Integer(ob)
    else:
        raise NotImplementedError()

def flatten(it):
    for a in it:
        if a.composite:
            for b in iter(a):
                yield b
        else:
            yield a

class Type(type):
    registry = {}

    __init__ = NotImplemented

    def __new__(meta, name, bases, dct):
        cls = type(name, bases, dct)
        Type.registry[name] = cls
        return cls

    @staticmethod
    def register(name, cls):
        assert name not in Type.registry
        Type.registry[name] = cls

# ==================================================================
# Base Types
# ==================================================================

class DataShape(object):
    __metaclass__ = Type

    composite = False
    name = False

    def __init__(self, operands=None, name=None):

        if type(operands) is DataShape:
            self.operands = operands

        elif len(operands) > 0:
            self.operands = tuple(flatten(operands))
            self.composite = True
        else:
            self.operands = tuple()
            self.composite = False

        if name:
            self.name = name
            self.__metaclass__.registry[name] = self

    def size(self):
        """
        In numpy, size would be a integer value. In Blaze the
        size is now a symbolic object

        A Numpy array of size (2,3) has size
            np.prod([2,3]) = 6
        A NDTable of datashape (a,b,2,3,int32) has size
            6*a*b
        """
        pass

    def __getitem__(self, index):
        return self.operands[index]

    def __getslice__(self, start, stop):
        return self.operands[start:stop]

    def __rmul__(self, other):
        if not isinstance(other, DataShape):
            other = shape_coerce(other)
        return product(other, self)

    def __mul__(self, other):
        if not isinstance(other, DataShape):
            other = shape_coerce(other)
        return product(other, self)

    def __str__(self):
        if self.name:
            return self.name
        else:
            return ' '.join(map(str, self.operands))

    def __eq__(self, other):
        if type(other) is DataShape:
            # Since we're iterable, just enumerate the dimension
            # specifiers and check them each individually if
            # every axis equals the other
            return all( a==b for a,b in izip(self, other) )
        else:
            return False

    def __repr__(self):
        return str(self)

class Atom(DataShape):
    abstract = True

    # Type constructor
    def __init__(self, *parameters):
        self.parameters = parameters

    def __str__(self):
        clsname = self.__class__.__name__
        return expr_string(clsname, self.parameters)

    def __repr__(self):
        return str(self)

# ==================================================================
# Native Types
# ==================================================================

class CType(DataShape):
    """
    Symbol for a sized type mapping uniquely to a native type.
    """

    def __init__(self, ctype, size=None):
        if size:
            assert 1 <= size < (2**23-1)
            label = ctype + str(size)
            self.parameters = [label]
            self.name = label
            Type.register(label, self)
        else:
            self.parameters = [ctype]
            self.name = ctype
            Type.register(ctype, self)

    def size(self):
        # TODO: no cheating!
        return dtype(self.name).itemsize

    def __str__(self):
        return str(self.parameters[0])

    def __eq__(self, other):
        if type(other) is CType:
            return self.parameters[0] == other.parameters[0]
        else:
            return False

    @property
    def type(self):
        raise NotImplementedError()

    @property
    def kind(self):
        raise NotImplementedError()

    @property
    def char(self):
        raise NotImplementedError()

    @property
    def num(self):
        raise NotImplementedError()

    @property
    def str(self):
        raise NotImplementedError()

    @property
    def byeteorder(self):
        raise NotImplementedError()


class Fixed(Atom):
    """
    Fixed dimension.
    """

    def __init__(self, i):
        assert isinstance(i, Integral)
        self.val = i
        self.parameters = [self.val]
        self.operands = [self.val]

    def __eq__(self, other):
        if type(other) is Fixed:
            return self.val == other.val
        else:
            return False

    def __str__(self):
        return str(self.val)

class Integer(Atom):
    """
    Integers, at the top level this means a Fixed dimension, at
    level of constructor it just means Integer in the sense of
    of machine integer.
    """

    def __init__(self, i):
        assert isinstance(i, Integral)
        self.val = i

    def free(self):
        return set([])

    def __eq__(self, other):
        if type(other) is Integer:
            return self.val == other.val
        else:
            return False

    def __str__(self):
        return str(self.val)

class TypeVar(Atom):
    """
    A free variable in the dimension specifier.
    """

    def __init__(self, symbol):
        self.symbol = symbol

    def free(self):
        return set([self.symbol])

    def __str__(self):
        return str(self.symbol)

    def __eq__(self, other):
        if isinstance(other, TypeVar):
            return self.symbol == other.symbol
        else:
            return False

class Bitfield(Atom):

    def __init__(self, size):
        self.size = size.val
        self.parameters = [size]

class Null(Atom):
    """
    Type a polymorphic missing value.
    """

    def __str__(self):
        return expr_string('NA', None)

class Bool(Atom):
    """
    Type level Bool ( i.e. for use in ternary expressions, not the
    same as the value-level bool ).
    """
    pass

class Either(Atom):
    """
    Taged union with two slots.
    """

    def __init__(self, a, b):
        self.a = a
        self.b = b
        self.parameters = [a,b]

# Internal-like range of dimensions, the special case of
# [0, inf) is aliased to the type Stream.
class Var(Atom):
    """
    Range type representing a bound or unbound interval of
    of possible Fixed dimensions.
    """

    def __init__(self, a, b=False):
        self.a = a.val
        if b:
            self.b = b.val
        else:
            self.b = b

        if a and b:
            assert self.a < self.b, 'Must have upper < lower'
        self.parameters = [self.a, self.b]

    @property
    def upper(self):
        # Just upper bound
        if self.b == False:
            return self.a

        # No upper bound case
        elif self.b == None:
            return float('inf')

        # Lower and upper bound
        else:
            return self.b

    @property
    def lower(self):
        # Just upper bound
        if self.b == False:
            return 0

        # No upper bound case
        elif self.b == None:
            return self.a

        # Lower and upper bound
        else:
            return self.a

    def __str__(self):
        return expr_string('Var', [self.lower, self.upper])

class Ternary(Atom):
    """
    Ternary expression.

        a ? (b, c)
        b if a else c
        With a : x -> Bool
    """

    def __init__(self, cond, rest):
        self.cond = cond
        self.rest = rest

        self.parameters = [cond, rest]

    def free(self):
        return map(free_vars, self.cond) | free_vars(self.rest)

    def __str__(self):
        return str(self.cond) + " ? (" + str(self.rest) +  ')'

class Function(Atom):
    """
    A arbitrary function to specify the dimension objects. Details of
    this are in flux. Not sure if embedding lambdas in the datashape is
    feasible.
    """

    # Same as Numba notation
    def __init__(self, argtypes, restype):
        self.arg_type = argtypes
        self.ret_type = restype

        self.parameters = [argtypes, restype]

    def free(self):
        return map(free_vars, self.arg_type) | free_vars(self.ret_type)

    def __str__(self):
        return str(self.arg_type) + " -> " + str(self.ret_type)

# Aggregate Types
# ===============

class Enum(Atom, Sequence):
    """
    A finite enumeration of Fixed dimensions that a datashape is over,
    in order.
    """

    def __str__(self):
        # Use c-style enumeration syntax
        return expr_string('', self.parameters, '{}')

    def __getitem__(self, index):
        return self.parameters[index]

    def __len__(self):
        return len(self.parameters)

class Union(Atom, Sequence):
    """
    C-style union
    """

    def __str__(self):
        return expr_string('', self.parameters, '{}')

    def __getitem__(self, index):
        return self.parameters[index]

    def __len__(self):
        return len(self.parameters)

class Record(DataShape, Mapping):
    """
    A composite data structure with fields mapped to types.
    """

    def __init__(self, **kwargs):
        self.d = kwargs
        self.k = kwargs.keys()
        self.v = kwargs.values()

    @property
    def fields(self):
        return self.d

    @property
    def names(self):
        return self.k

    def free(self):
        return set(self.k)

    def __eq__(self, other):
        if isinstance(other, Record):
            return self.d == other.d
        else:
            return False

    def __call__(self, key):
        return self.d[key]

    def __iter__(self):
        return zip(self.k, self.v)

    def __len__(self):
        return len(self.k)

    def __str__(self):
        return 'Record ( ' + ''.join([('%s = %s, ' % (k,v)) for k,v in zip(self.k, self.v)]) + ')'

    def __repr__(self):
        return 'Record ' + repr(self.d)

# Memory Types
# ============

class RemoteSpace(object):
    def __init__(self, blaze_uri):
        pass

class LocalMemory(object):
    def __init__(self):
        self.bounds = ( 0x0, 0xffffffffffffffff )

class SharedMemory(object):
    def __init__(self, key):
        # something like:
        # shmid = shmget(key)
        # shmat(shmid, NULL, 0)
        self.bounds = ( 0x0, 0x1 )

class Ptr(Atom):
    """
    Type*
    Type Addrspace*

    Usage:
    ------
    Pointer to a integer in local memory
        *int32

    Pointer to a 4x4 matrix of integers in local memory
        *(4, 4, int32)

    Pointer to a record in local memory
        *{x: int32, y:int32, label: string}

    Pointer to integer in a shared memory segement keyed by 'foo'
        *(int32 (shm 'foo'))

    Pointer to integer on a array server 'bar'
        *(int32 (rmt array://bar))
    """

    def __init__(self, pointee, addrspace=None):
        self.pointee = pointee

        if addrspace:
            self.addrspace = addrspace
            self.parameters = [pointee, addrspace]
        else:
            self.parameters = [pointee]
            self.addrspace = LocalMemory()

    @property
    def byte_bounds(self):
        return self.addrspace.bounds

    @property
    def local(self):
        return isinstance(self.addrspace, LocalMemory())

    @property
    def remote(self):
        return isinstance(self.addrspace, RemoteSpace())

# Class derived Records
# =====================
# They're just records but can be constructed like Django models.

def derived(sig):
    from parse import parse
    sig = parse(sig)
    def a(fn):
        return sig
    return a


# Constructions
# =============

# Right now we only have one operator (,) which constructs
# product types ( ie A * B ). We call these dimensions.

# It is neccesarry that if forall z = x * y then
#   fst(z) * snd(z) = z

# product :: A -> B -> A * B
def product(A,B):
    if A.composite and B.composite:
        f = A.operands
        g = B.operands

    elif A.composite:
        f = A.operands
        g = (B,)

    elif B.composite:
        f = (A,)
        g = B.operands

    else:
        f = (A,)
        g = (B,)

    return DataShape(operands=(f+g))

# fst :: A * B -> A
def fst(ds):
    return ds[0]

# snd :: A * B -> B
def snd(ds):
    return ds[1:]

# Coproduct is the dual to the (,) operator. It constructs sum
# types ( ie A + B ).
def coprod(A, B):
    return Either(A,B)

# left  :: A + B -> A
def left(ds):
    return ds.parameters[0]

# right :: A + B -> B
def right(ds):
    return ds.parameters[1]

# Machines Types
# ==============
# At the type level these are all singleton types, they take no
# arguments in their constructors.

word = int(architecture()[0][0:2])

int_       = CType('int')
float_     = CType('float')
long_      = CType('long')
bool_      = CType('bool')
double     = CType('double')
short      = CType('short')
longdouble = CType('longdbouble')
char       = CType('char')

uint       = CType('uint')
ulong      = CType('ulong')
ulonglong  = CType('ulonglong')

int8       = CType('int', 8)
int16      = CType('int', 16)
int32      = CType('int', 32)
int64      = CType('int', 64)

uint8      = CType('uint',  8)
uint16     = CType('uint', 16)
uint32     = CType('uint', 32)
uint64     = CType('uint', 64)

float8       = CType('float', 8)
float16      = CType('float', 16)
float32      = CType('float', 32)
float64      = CType('float', 64)
float128     = CType('float', 128)

complex64  = CType('complex' , 64)
complex128 = CType('complex', 128)
complex256 = CType('complex', 256)

void       = CType('void')
pyobj      = CType('PyObject')

# TODO: differentiate between fixed-length and variable-length
# strings.
string     = CType('string')

na = nan = Null
Stream = Var(Integer(0), None)

# *the* null record, # since we need
#   {} is {} = True
NullRecord = Record()

Type.register('NA', Null)
Type.register('Bool', Bool)
Type.register('Stream', Stream)

# Shorthand

O = pyobj
b1 = bool_

i1 = int8
i2 = int16
i4 = int32
i8 = int64

u1 = uint8
u2 = uint16
u4 = uint32
u8 = uint64

f1 = float8
f2 = float16
f4 = float32
f8 = float64
f16 = float128

f = float_
d = double

c8  = complex64
c16 = complex128
c32 = complex256

S = string

# Downcast a datashape object into a Numpy
# (shape, dtype) tuple if possible.
# i.e.
#   5,5,in32 -> ( (5,5), dtype('int32') )

# TODO: numpy structured arrays
def to_numpy(ds):
    shape = tuple()
    dtype = None

    assert isinstance(ds, DataShape)
    for dim in ds:
        if isinstance(dim, Integer):
            shape += (dim,)
        if isinstance(dim, CType):
            dtype += (dim,)

    assert len(shape) > 0 and dtype, "Could not convert"
    return (shape, dtype)

# Upconvert a datashape object into a Numpy
# (shape, dtype) tuple if possible.
# i.e.
#   5,5,in32 -> ( (5,5), dtype('int32') )
def to_datashape(shape, dtype):
    import numpy as np

    # TODO: use rosetta stones
    ReverseLookupDict({
        np.int32: int32,
        np.float: float,
    })
    return dtype*shape
