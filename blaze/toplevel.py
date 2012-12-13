import os, os.path
import uuid

from urlparse import urlparse
from params import params, to_cparams
from params import params as _params
from sources.sql import SqliteSource
from sources.chunked import CArraySource

from table import NDArray, Array
from blaze.datashape.coretypes import from_numpy, to_numpy
from blaze import carray, dshape as _dshape

import numpy as np

def open(uri=None):

    if uri is None:
        source = CArraySource()
    else:
        uri = urlparse(uri)

        if uri.scheme == 'carray':
            path = os.path.join(uri.netloc, uri.path[1:])
            parms = params(storage=path)
            source = CArraySource(params=parms)

        elif uri.scheme == 'sqlite':
            path = os.path.join(uri.netloc, uri.path[1:])
            parms = params(storage=path or None)
            source = SqliteSource(params=parms)

        else:
            # Default is to treat the URI as a regular path
            parms = params(storage=uri.path)
            source = CArraySource(params=parms)

    # Don't want a deferred array (yet)
    # return NDArray(source)
    return Array(source)

# These are like NumPy equivalent except that they can allocate
# larger than memory.

def zeros(dshape, params=None):
    """ Create an Array and fill it with zeros.
    """
    if isinstance(dshape, basestring):
        dshape = _dshape(dshape)
    shape, dtype = to_numpy(dshape)
    cparams, rootdir, format_flavor = to_cparams(params or _params())
    if rootdir is not None:
        carray.zeros(shape, dtype, rootdir=rootdir, cparams=cparams)
        return open(rootdir)
    else:
        source = CArraySource(carray.zeros(shape, dtype, cparams=cparams),
                              params=params)
        return Array(source)

def ones(dshape, params=None):
    """ Create an Array and fill it with ones.
    """
    if isinstance(dshape, basestring):
        dshape = _dshape(dshape)
    shape, dtype = to_numpy(dshape)
    cparams, rootdir, format_flavor = to_cparams(params or _params())
    if rootdir is not None:
        carray.ones(shape, dtype, rootdir=rootdir, cparams=cparams)
        return open(rootdir)
    else:
        source = CArraySource(carray.ones(shape, dtype, cparams=cparams),
                              params=params)
        return Array(source)

def loadtxt(filetxt, storage):
    """ Convert txt file into Blaze native format """
    Array(np.loadtxt(filetxt), params=params(storage=storage))
