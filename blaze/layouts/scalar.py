"""
Scalar layouts are arangements of scalar matrix data on to blocks
of memory that may or may not be contigious. The only requirement
of a layout is that there be some unique way of distinguishing an
"initial element" in the container from which to orient.
"""

import abc
import math
from numpy import zeros
from pprint import pformat
from collections import defaultdict
from bisect import bisect_left, insort_left
from numpy import searchsorted
from blaze.layouts.layout import Layout

#------------------------------------------------------------------------
# Coordinate Transformations
#------------------------------------------------------------------------


def ctranslate(factor, axi):
    """
    A coordinate translation.
    """
    # (i,j, ...) -> (i + a0 , j + a1, ...)

    # TODO: Certainly better way to write this...
    def T(xs):
        zs = xs[:]
        for x, j in zip(xrange(len(zs)), axi):
            if j == 1:
                zs[x] = zs[x] + factor
        return zs

    def Tinv(xs):
        zs = xs[:]
        for y, j in zip(xrange(len(zs)), axi):
            if j == 1:
                zs[y] = zs[y] - factor
        return zs

    return T, Tinv

def ctranspose(axi):

    def T(xs):
        xs = list(xs)
        xs[0] = xs[1]
        return xs

    # Transpose is self inverse
    Tinv = T
    return T, Tinv

def cdimshuffle(axi, mapping):
    """
    Example::

        f : 2, 0, 1 : [1,2,3] -> [3,1,2]
        g : 2, 0, 1 : [3,1,2] -> [1,2,3]
    """

    imapping = invert(mapping)

    def T(xs):
        zs = list(xs)
        for j in mapping:
            zs[j] = xs[j]
        return zs

    def Tinv(xs):
        zs = list(xs)
        for j in mapping:
            zs[j] = xs[j]
        return zs

    return T, Tinv

def splitl(lst, n):
    return lst[0:n], lst[n], lst[n:-1]

def stack_transforms(c1,c2, axis):
    """
    Stack two intervals to form a large interval
    """
    #   p       q        p   q
    # [1,2] | [1,2] -> [1,2,3,4]

    i1, i2 = c1.inf, c2.inf
    s1, s2 = c1.sup, c2.sup

    n = abs(i2-s1)
    assert n > 0

    xs = list(axis)

    T, Tinv = ctranslate(n, xs)
    return T, Tinv

#------------------------------------------------------------------------
# Scalar Interval
#------------------------------------------------------------------------

class Interval(object):
    """
    A mathematical interval uniquely defined by two parameters

    Parameters

        :inf: lower bound

        :sup: upper bound
    """
    def __init__(self, inf, sup):
        self.inf = inf
        self.sup = sup

    def __add__(self, n):
        """
        Shift the interval
        """
        return Interval(self.inf + n, self.sup + n)

    def __mul__(self, n):
        """
        Dilate the interval
        """
        return Interval(self.inf * n, self.sup * n)

    def __repr__(self):
        return 'i[%i,%i]' % (self.inf, self.sup)

def hull(i1, i2):
    return Interval(min(i1.inf, i2.inf), max(i1.sup, i2.sup))

#------------------------------------------------------------------------
# Coordinate Mappings
#------------------------------------------------------------------------

class Chart(object):
    """
    A interval partition pointing at a Indexable reference.
    """
    def __init__(self, components, ref, tinv=None):
        self.ref = ref

        if not tinv:
            self.tinv = None
            # We're at the bottom turtle
            self.transformed = False
        else:
            self.tinv = tinv
            self.transformed = True

        self.components = components

    def transform(self, t, tinv):
        """
        Returns a new chart with coordinates transformed.
        """
        coords = t(self.components)
        return Chart( coords, self.ref, tinv)

    def iterdims(self):
        """
        Enumerate the components, yielding the dimension index
        and the component.
        """
        return enumerate(self.components)

    # Lift a set of coordinates into the "chart" space
    def inverse(self, coords):
        """
        Invert the given coordinates per the inverse transform
        function associated with this chart.
        """
        assert self.tinv, \
            "Chart does not have coordinate inverse transform function"
        return self.tinv(coords)

    def __getitem__(self, indexer):
        return self.ref[indexer]

    def __repr__(self):
        return 'Chart( %s )' % ' x '.join(map(repr,self.components))


#------------------------------------------------------------------------
# Contiguous Layouts
#------------------------------------------------------------------------


class ContiguousL(Layout):
    """
    A single block with. Coordinate transform is just a passthrough.
    """
    wraparound = False
    boundscheck = False

    def __init__(self, single):
        self.bounds     = []
        self.partitions = []
        self.init = single
        self.points = {}

    def change_coordinates(self, indexer):
        """
        Identity coordinate transform
        """
        return self.init, indexer

    @property
    def desc(self):
        return 'Identity'

class StridedL(Layout):
    """
    Single strided layout. This behaves like strided NumPy arrays.
    """

    def __init__(self, init, strides=None):
        self.bounds     = []
        self.partitions = []
        self.init = init
        self.strides = strides
        self.points = {}

    def change_coordinates(self, indexer):
        """
        Identity coordinate transform
        """
        raise NotImplementedError

    @property
    def desc(self):
        return 'Strided(%r)' % self.strides

#------------------------------------------------------------------------
# Chunked Layouts
#------------------------------------------------------------------------

class ChunkedL(Layout):
    """
    Chunked layout, like CArray.

    Parameters
    ----------

        :init: Initial block

        :cdimension: Dimension along which chunks are aligned.
                     CArraySource uses 0 by default.

    """
    wraparound = False
    boundscheck = False

    def __init__(self, init, cdimension):
        self.init = init
        self.partitions = init.partitions
        self.cdimension = cdimension
        self.points = {}

    def change_coordinates(self, indexer):
        """
        Identity coordinate transform
        """
        return self.init, indexer

    @property
    def desc(self):
        return 'Chunked(dim=%i)' % self.cdimension


class MultichunkedL(Layout):
    """
    MultichunkL is a layout to contain multiple possibly unaligned
    chunks. It is enough to track the partition points of the
    array in arbitrary dimensions and then binary sort across
    each dimension in order to resolve partition locations.
    """
    wraparound = False
    boundscheck = False

    def __init__(self, partitions, ndim):
        # The numeric (x,y,z) coordinates of ith partition point
        self.ppoints = defaultdict(list)
        # The partition associated with the ith partition point
        self.points = defaultdict(list)

        self.bounds = []
        self.ndim   = ndim

        self.partitions = partitions

        # The zero partition
        self.init = None

        # Build up the partition search, for each dimension
        for a in partitions:
            self.init = self.init or a
            for i, b in enumerate(a.components):
                # (+1) because it's the infinum
                insort_left(self.points[i] , a)
                insort_left(self.ppoints[i], b.inf+1)

        # Build the bounds as well
        self.bounds = map(self.bounds_dim, xrange(ndim))

    def iter_components(self, i):
        """ Iterate through the components of each partition.  """

        return [a.components[i] for a in self.partitions]

    def bounds_dim(self, i):
        return reduce(hull, self.iter_components(i))

    def transform(self, T, tinv):
        tpoints = defaultdict(list)

        for i, p in self.points.iteritems():
            tpoints[i] = T(p)

        T(self.bounds)

        return Layout(self.partitions, self.ndim)

    def change_coordinates(self, indexer):
        """
        Change coordinates into the block we're indexing into.
        """
        # use xrange/len because we are mutating it
        indexerl = xrange(len(indexer))

        for i in indexerl:

            idx = indexer[i]
            space = self.points[i]
            partitions = self.ppoints[i]
            size = len(space)

            # Partition index
            pdx = bisect_left(partitions, idx)

            # Edge cases
            if pdx <= 0:
                chart = space[0]
            if pdx >= size:
                chart = space[-1]
            else:
                chart = space[pdx]

            if chart.transformed:
                return chart.ref, chart.inverse(indexer)
            else:
                continue

        return self.init.ref, indexer

    # TODO: use byte interfaces!
    def __getitem__(self, indexer):
        coords = self.change_coordinates(indexer)
        return coords

    @property
    def desc(self):
        return 'Multichunked(points=%r)' % self.points

#------------------------------------------------------------------------
# Fractal Layouts
#------------------------------------------------------------------------

# Fractal layouts are really really interesting for us because they are
# data layouts that we could never do with NumPy since it necessarily
# requires a system for doing more complicated index space transforms.

def rot(n, x, y, rx, ry):
    if ry == 0:
        if rx == 1:
            x = n-1 - x
            y = n-1 - y
        x, y = y, x
    return x,y

def xy2d(order, x, y):
    n = order / 2
    d = 0
    while n > 0:
        rx = 1 if (x & n) else 0
        ry = 1 if (y & n) else 0
        d += n * n * ((3 * rx) ^ ry)
        x,y = rot(n, x, y, rx, ry)
        n /= 2
    return d

class HilbertL(Layout):
    """
    Simple Hilbert curve layout. Hilbert curves preserve index locality
    but are discontinuous.

    Example of a order 4 (H_4) curve over a 2D array::

         0    3    4    5
         1    2    7    6
        14   13    8    9
        15   12   11   10

         +    +---------+
         |    |         |
         +----+    +----+
                   |
         +----+    +----+
         |    |         |
         +    +----+----+

    """

    def __init__(self, init, size):
        self.bounds     = [size, size]
        self.partitions = []
        self.init = init
        self.points = {}
        self.order = 2**int(math.ceil(math.log(size, 2)))

    def change_coordinates(self, indexer):
        assert len(indexer) <= 2, 'Only defined for 2D indexes'
        x,y = indexer
        if self.boundscheck:
            if x >= self.order or y >= self.order:
                raise IndexError('Outside of bounds')
        return self.init, xy2d(self.order, x, y)

    @property
    def desc(self):
        return 'Hilbert'

#------------------------------------------------------------------------
# Z-Order
#------------------------------------------------------------------------

# See http://graphics.stanford.edu/~seander/bithacks.html
mask1 = 0x0000ffff
mask2 = 0x55555555

def mask(n):
    n &= mask1
    n = (n | (n << 8)) & 0x00FF00FF
    n = (n | (n << 4)) & 0x0F0F0F0F
    n = (n | (n << 2)) & 0x33333333
    n = (n | (n << 1)) & 0x55555555
    return n

def unmask(n):
    n &= mask2
    n = (n ^ (n >> 1)) & 0x33333333
    n = (n ^ (n >> 2)) & 0x0F0F0F0F
    n = (n ^ (n >> 4)) & 0x00FF00FF
    n = (n ^ (n >> 8)) & 0x0000FFFF
    return n

def encode(x, y):
    return mask(x) | (mask(y) << 1)

def decode(n):
    return unmask(n), unmask(n >> 1)

def zorder(x, y):
   ret = 0
   for bit in xrange(0, 8):
       ret |= ( ( ( x & 1 ) << 1 ) | ( y & 1 ) ) << ( bit << 1 )
       x >>= 1
       y >>= 1
   return ret

class ZIndexL(Layout):

    @property
    def desc(self):
        return 'Z-Order'

#------------------------------------------------------------------------
# Block Combinations
#------------------------------------------------------------------------

def nstack(n, a, b):

    adim = len(a.components)
    bdim = len(b.components)

    assert adim == bdim, 'For now must be equal'
    ndim = adim

    try:
        a0, a1, a2 = splitl(a.components, n)
        b0, b1, b2 = splitl(b.components, n)
    except IndexError:
        raise Exception("Axis %i does not exist" % n)

    axis = zeros(len(a.components))
    axis[n] = 1

    T, Tinv = stack_transforms(a1, b1, list(axis))
    bT = b.transform(T, Tinv)
    assert bT.tinv

    return MultichunkedL([a, bT], ndim)

def vstack(a, b):
    return nstack(0, a, b)

def hstack(a, b):
    return nstack(1, a, b)

def dstack(a, b):
    return nstack(2, a, b)
