import numpy as np
from blaze import dshape
from blaze import NDTable, Table, NDArray, Array

def test_all_construct():
    expected_ds = dshape('3, int')

    a = NDArray([1,2,3])
    str(a)
    repr(a)
    a.datashape._equal(expected_ds)

    a = Array([1,2,3])
    str(a)
    repr(a)
    a.datashape._equal(expected_ds)


    data = np.zeros((2,),dtype=[('A', 'i4'),('B', 'f4'),('C', 'S')])
    a = NDTable(data)
    str(a)
    repr(a)
    a.datashape._equal(expected_ds)

    #a = Table([1,2,3])
    #str(a)
    #repr(a)
    #a.datashape._equal(expected_ds)
