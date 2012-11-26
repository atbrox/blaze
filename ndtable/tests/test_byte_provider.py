"""
Test the internals of constructing arrays from various byte
providers sources. These interfaces would not normally be exposed
to the end-user.
"""

import numpy as np
import ndtable.carray as ca

from ndtable.datashape import dshape
from ndtable.table import NDArray, Array
from ndtable.sources.canonical import PythonSource, ByteSource, \
    CArraySource, ArraySource

# TODO: move NDArray -> Array

def test_from_carray():
    b1 = CArraySource([1,2,3])

    nd = Array._from_providers(b1)

def test_from_numpy():
    c1 = np.array([1,2])
    b1 = ArraySource(c1)

    nd = Array._from_providers(b1)

def test_from_bytes():
    #bits = bytes(np.ones((2,2), dtype=np.dtype('int32')).data)
    bits = b'\x01\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00'
    b1 = ByteSource(bits)

    nd = Array._from_providers(b1)

def test_from_python():
    b1 = PythonSource([1,2])
    b2 = PythonSource([3,4])

    nd = Array._from_providers(b1, b2)
