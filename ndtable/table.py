from bytei import ByteProvider
from datashape.coretypes import Type, Fixed, Var, TypeVar, \
    DataShape
from idx import AutoIndex, Space, Subspace
from sources.canonical import RawSource
from idx import Indexable

class CannotEmbed(Exception):
    def __init__(self, space, dim):
        self.space = space
        self.dim   = dim

    def __str__(self):
        return "Cannot embed space of values (%r) in (%r)" % (
            self.space, self.dim
        )

def describe(obj):

    if isinstance(obj, DataShape):
        return obj

    elif isinstance(obj, list):
        return Fixed(len(obj))

    elif isinstance(obj, tuple):
        return Fixed(len(obj))

    elif isinstance(obj, DataTable):
        return obj.datashape

def can_embed(obj, dim2):
    """
    Can we embed a ``obj`` inside of the space specified by the outer
    dimension ``dim``.
    """
    dim1 = describe(obj)

    # We want explicit fallthrough
    if isinstance(dim1, Fixed):

        if isinstance(dim2, Fixed):
            if dim1 == dim2:
                return True

        if isinstance(dim2, Var):
            if dim2.lower < dim1.val < dim2.upper:
                return True

    if isinstance(dim1, TypeVar):
        return True

    raise CannotEmbed(dim1, dim2)

class IndexArray(object):
    """
    A numpy array without math functions
    """
    pass

class Table(object):
    """
    Deferred evaluation table that constructs the expression
    graph.
    """
    pass

class DataTable(object):
    """
    A reified Table.
    """
    def __init__(self, obj, datashape, index=None, metadata=None):
        self.datashape = datashape
        self.metadata = metadata

        if isinstance(obj, Indexable):
            self.space = obj
        elif isinstance(obj, ByteProvider):
            self.space = obj
        elif isinstance(obj, list):
            self.space = []

    @staticmethod
    def from_providers(shape, *providers):
        """
        Create a DataTable from a 1D list of byte providers.
        """
        subspaces = []
        indexes   = []

        ntype    = shape[-1]
        innerdim = shape[1]
        outerdim = shape[0]

        # The number of providers must be compatable ( not neccessarily
        # equal ) with the number of given providers.
        assert can_embed(providers, outerdim)

        for i, provide in enumerate(providers):
            # Make sure we don't go over the outer dimension

            # (+1) because we don't usually consider 0 dimension
            # as 1
            assert (i+1) < outerdim

            subspace = Subspace(provide)
            substructure = subspace.size(ntype)

            # Can we embed the substructure inside of the of the inner
            # dimension?
            assert can_embed(substructure, innerdim)

            subspaces += [subspace]

        # ???
        metadata = {}

        space = Space(*subspaces)
        return DataTable(space, shape, indexes, metadata)

    @staticmethod
    def from_sql(dburl, query):
        pass

    @staticmethod
    def from_csv(fname, *params):
        pass

    # IPython notebook integration
    def to_html(self):
        return '<table><th>DataTable!</th></table>'

    def _repr_html_(self):
        return ('<div style="max-height:1000px;'
                'max-width:1500px;overflow:auto;">\n' +
                self.to_html() + '\n</div>')
