"""
This defines the DataShape type system.
"""

import numpy as np

import datetime
from struct import calcsize
from numbers import Integral
from collections import Mapping, Sequence

from blaze.error import NotNumpyCompatible

try:
    from numba.minivect import minitypes
    have_minivect = True
except ImportError:
    have_minivect = False

#------------------------------------------------------------------------
# Type Metaclass
#------------------------------------------------------------------------

class Type(type):
    _registry = {}

    __init__ = NotImplemented

    def __new__(meta, name, bases, dct):
        cls = type(name, bases, dct)

        # Don't register abstract classes
        if not dct.get('abstract'):
            Type._registry[name] = cls
            return cls

    @staticmethod
    def register(name, type):
        # Don't clobber existing types.
        # TODO: more sophisticated ways of namespacing these.
        if name in Type._registry:
            raise TypeError('There is another type registered with name %s'\
                % name)

        Type._registry[name] = type

    @classmethod
    def lookup_type(cls, name):
        return cls._registry[name]

#------------------------------------------------------------------------
# Primitives
#------------------------------------------------------------------------

class Primitive(object):
    composite = False
    __metaclass__ = Type

    def __init__(self, *parameters):
        self.parameters = parameters

    def __rmul__(self, other):
        if not isinstance(other, (DataShape, Primitive)):
            other = shape_coerce(other)
        return product(other, self)

    def __mul__(self, other):
        if not isinstance(other, (DataShape, Primitive)):
            other = shape_coerce(other)
        return product(other, self)

class Null(Primitive):
    """
    The null datashape.
    """
    def __str__(self):
        return expr_string('null', None)

class Integer(Primitive):
    """
    Integers, at the top level this means a Fixed dimension, at
    level of constructor it just means integer in the sense of
    of just an integer value.
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

class Dynamic(Primitive):
    """
    The dynamic type allows an explicit upcast and downcast from any
    type to ``?``. This is normally not allowed in most static type
    systems.
    """

    def __str__(self):
        return '?'

    def __repr__(self):
        # emulate numpy
        return ''.join(["dshape(\"", str(self), "\")"])

# Top is kind of an unfortunate term because our system is very much
# *not* a hierarchy, but this is the entrenched term so we use it.

class Top(Primitive):

    def __str__(self):
        return 'top'

    def __repr__(self):
        # emulate numpy
        return ''.join(["dshape(\"", str(self), "\")"])

#------------------------------------------------------------------------
# Base Types
#------------------------------------------------------------------------

class DataShape(object):
    __metaclass__ = Type

    composite = False
    name = False

    def __init__(self, parameters=None, name=None):

        if type(parameters) is DataShape:
            self.paramaeters = parameters

        elif len(parameters) > 0:
            self.parameters = tuple(flatten(parameters))
            self.composite = True
        else:
            self.parameters = tuple()
            self.composite = False

        if name:
            self.name = name
            self.__metaclass__._registry[name] = self

    def __getitem__(self, index):
        return self.parameters[index]

    # TODO these are kind of hackish, remove
    def __rmul__(self, other):
        if not isinstance(other, (DataShape, Primitive)):
            other = shape_coerce(other)
        return product(other, self)

    def __mul__(self, other):
        if not isinstance(other, (DataShape, Primitive)):
            other = shape_coerce(other)
        return product(other, self)

    def __str__(self):
        if self.name:
            return self.name
        else:
            return ', '.join(map(str, self.parameters))

    def _equal(self, other):
        """ Structural equality """
        return all(a==b for a,b in zip(self, other))

    def __eq__(self, other):
        if type(other) is DataShape:
            return False
        else:
            raise TypeError('Cannot compare non-datashape to datashape')

    def __repr__(self):
        return ''.join(["dshape(\"", str(self), "\")"])

class Atom(DataShape):
    """
    Atoms for arguments to constructors of types, not types in
    and of themselves. Parser artifacts, if you like.
    """
    abstract = True

    def __init__(self, *parameters):
        self.parameters = parameters

    def __str__(self):
        clsname = self.__class__.__name__
        return expr_string(clsname, self.parameters)

    def __repr__(self):
        return str(self)

#------------------------------------------------------------------------
# Native Types
#------------------------------------------------------------------------

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

    @classmethod
    def from_str(self, s):
        """
        To Numpy dtype.

        >>> CType.from_str('int32')
        int32
        """
        return Type._registry[s]

    @classmethod
    def from_dtype(self, dt):
        """
        From Numpy dtype.

        >>> CType.from_dtype(dtype('int32'))
        int32
        """
        return Type._registry[dt.name]

    def size(self):
        # TODO: no cheating!
        return np.dtype(self.name).itemsize

    def to_struct(self):
        """
        To struct code.
        """
        return np.dtype(self.name).char

    def to_dtype(self):
        """
        To Numpy dtype.
        """
        # special cases because of NumPy weirdness
        # >>> dtype('i')
        # dtype('int32')
        # >>> dtype('int')
        # dtype('int64')
        if self.name == "int":
            return np.dtype("i")
        if self.name == "float":
            return np.dtype("f")
        return np.dtype(self.name)

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

#------------------------------------------------------------------------
# Fixed
#------------------------------------------------------------------------

class Fixed(Atom):
    """
    Fixed dimension.
    """

    def __init__(self, i):
        assert isinstance(i, Integral)
        self.val = i
        self.parameters = [self.val]

    def __eq__(self, other):
        if type(other) is Fixed:
            return self.val == other.val
        else:
            return False

    def __str__(self):
        return str(self.val)

#------------------------------------------------------------------------
# Variable
#------------------------------------------------------------------------

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

# Internal-like range of dimensions, the special case of
# [0, inf) is aliased to the type Stream.
class Range(Atom):
    """
    Range type representing a bound or unbound interval of
    of possible Fixed dimensions.
    """

    def __init__(self, a, b=False):
        if type(a) is int:
            self.a = a
        else:
            self.a = a.val

        if type(b) is int:
            self.b = b
        elif b is False or b is None:
            self.b = b
        else:
            self.b = b.val

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
        return expr_string('Range', [self.lower, self.upper])

#------------------------------------------------------------------------
# Aggregate
#------------------------------------------------------------------------

class Either(Atom):
    """
    Taged union with two slots.
    """

    def __init__(self, a, b):
        self.a = a
        self.b = b
        self.parameters = [a,b]

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
    A union of possible datashapes that may occupy the same
    position.
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
        # Prints out something like this:
        #   {a : int32, b: float32, ... }
        return ('{ '
            + ''.join([
                ('%s : %s, ' % (k,v)) for k,v in zip(self.k, self.v)
        ]) + '}')

    def __repr__(self):
        return 'Record ' + repr(self.d)

#------------------------------------------------------------------------
# Constructions
#------------------------------------------------------------------------

def product(A, B):
    if A.composite and B.composite:
        f = A.parameters
        g = B.parameters

    elif A.composite:
        f = A.parameters
        g = (B,)

    elif B.composite:
        f = (A,)
        g = B.parameters

    else:
        f = (A,)
        g = (B,)

    return DataShape(parameters=(f+g))

def from_python_scalar(scalar):
    """
    Return a datashape ctype for a python scalar.
    """
    if isinstance(scalar, int):
        return int_
    elif isinstance(scalar, float):
        return double
    elif isinstance(scalar, complex):
        return complex128
    elif isinstance(scalar, (str, unicode)):
        return string
    elif isinstance(scalar, datetime.timedelta):
        return timedelta64
    elif isinstance(scalar, datetime.datetime):
        return datetime64
    else:
        return pyobj

#------------------------------------------------------------------------
# Unit Types
#------------------------------------------------------------------------

# At the type level these are all singleton types, they take no
# arguments in their constructors and have no internal structure.

plat = calcsize('@P') * 8

int_       = CType('int')
long_      = CType('long')
bool_      = CType('bool')
float_     = CType('float')
double     = CType('double')
short      = CType('short')
char       = CType('char')

int8       = CType('int', 8)
int16      = CType('int', 16)
int32      = CType('int', 32)
int64      = CType('int', 64)

uint8      = CType('uint',  8)
uint16     = CType('uint', 16)
uint32     = CType('uint', 32)
uint64     = CType('uint', 64)

float16    = CType('float', 16)
float32    = CType('float', 32)
float64    = CType('float', 64)
float128   = CType('float', 128)

# NOTE: Naming these 'int' and 'float' is a *really* bad idea.
# NOTE: People expect 'float' to be a native float. This is also
# NOTE: inconsistent with Numba.
# if plat == 32:
#     int_ = int32
#     uint = uint32
#     float_ = float32
# else:
#     int_ = int64
#     uint = uint64
#     float_ = float64

complex64  = CType('complex' , 64)
complex128 = CType('complex', 128)
complex256 = CType('complex', 256)

timedelta64 = CType('timedelta', 64)
datetime64 = CType('datetime', 64)

ulonglong  = CType('ulonglong')
longdouble = float128

void = CType('void')
object_ = pyobj = CType('object')

string = CType('string')

na = Null
top = Top()
dynamic = Dynamic()
NullRecord = Record()

Stream = Range(Integer(0), None)

Type.register('NA', Null)
Type.register('Stream', Stream)
Type.register('?', Dynamic)

# Top should not be user facing... but for debugging useful
Type.register('top', top)

#------------------------------------------------------------------------
# Extraction
#------------------------------------------------------------------------

#  Dimensions
#      |
#  ----------
#  1, 2, 3, 4,  int32
#               -----
#                 |
#              Measure

def extract_dims(ds):
    """ Discard measure information and just return the
    dimensions
    """
    if isinstance(ds, CType):
        raise Exception("No Dimensions")
    return ds.parameters[0:-2]

def extract_measure(ds):
    """ Discard shape information and just return the measure
    """
    if isinstance(ds, CType):
        return ds
    return ds.parameters[-1]

def is_simple(ds):
    # Unit Type
    if not ds.composite:
        if isinstance(ds, (Fixed, Integer, CType)):
            return True

    # Composite Type
    else:
        for dim in ds:
            if not isinstance(dim, (Fixed, Integer, CType)):
                return False
        return True

#------------------------------------------------------------------------
# Minivect Compatibility
#------------------------------------------------------------------------

def to_minitype(ds):
    # To minitype through NumPy. Discards dimension information.
    return minitypes.map_dtype(to_numpy(extract_measure(ds)))

def to_minivect(ds):
    raise NotImplementedError
    #return (shape, minitype)

#------------------------------------------------------------------------
# NumPy Compatibility
#------------------------------------------------------------------------

def to_dtype(ds):
    """ Throw away the shape information and just return the
    measure as NumPy dtype instance."""
    return to_numpy(extract_measure(ds))

def promote(*operands):
    """
    Take an arbitrary number of graph nodes and produce the promoted
    dtype by discarding all shape information and just looking at the
    measures.

    ::

        5, 5,  | int   |
        2, 5,  | int   |
        1, 3,  | float |

    >>> promote(IntNode(1), Op(IntNode(2))
    int
    >>> promote(FloatNode(1), Op(IntNode(2))
    float
    """

    # Looks something like this...

    # (ArrayNode, IntNode...) -> (dshape('2, int', dshape('int'))
    # (dshape('2, int', dshape('int')) -> (dshape('int', dshape('int'))
    # (dshape('2, int', dshape('int')) -> (dtype('int', dtype('int'))

    types    = (op.simple_type() for op in operands)
    measures = (extract_measure(t) for t in types)
    dtypes   = (to_numpy(m) for m in measures)

    promoted = reduce(np.promote_types, dtypes)
    datashape = CType.from_dtype(promoted)
    return datashape

def to_numpy(ds):
    """
    Downcast a datashape object into a Numpy (shape, dtype) tuple if
    possible.

    >>> to_numpy(dshape('5, 5, int32'))
    (5,5), dtype('int32')
    """

    if isinstance(ds, CType):
        return ds.to_dtype()

    shape = tuple()
    dtype = None

    #assert isinstance(ds, DataShape)
    for dim in ds:
        if isinstance(dim, (Fixed, Integer)):
            shape += (dim,)
        elif isinstance(dim, CType):
            dtype = dim.to_dtype()
        else:
            raise NotNumpyCompatible()

    if len(shape) < 0 or dtype == None:
        raise NotNumpyCompatible()
    return (shape, dtype)


def from_numpy(shape, dt):
    """
    Upcast a (shape, dtype) tuple if possible.

    >>> from_numpy((5,5), dtype('int32'))
    dshape('5, 5, int32')
    """
    dt = np.dtype(dt)

    if shape == ():
        dimensions = []
    else:
        dimensions = map(Fixed, shape)

    measure = CType.from_dtype(dt)

    return reduce(product, dimensions + [measure])

#------------------------------------------------------------------------
# Printing
#------------------------------------------------------------------------

def expr_string(spine, const_args, outer=None):
    if not outer:
        outer = '()'

    if const_args:
        return str(spine) + outer[0] + ','.join(map(str,const_args)) + outer[1]
    else:
        return str(spine)

#------------------------------------------------------------------------
# Argument Munging
#------------------------------------------------------------------------

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


def table_like(ds):
    return type(ds[-1]) is Record

def array_like(ds):
    return not table_like(ds)
