

# A dummy typing system so we can document types of attributes
def _dummy(*args, **kw): pass
Enum = Int = Float = Str = Tuple = Bool = _dummy

class DataDescriptor(object):
    """ DataDesciptors are the underlying, low-level references to data
    that is returned by manifest Indexable objects (i.e. objects backed
    by real data of some variety).

    Whereas traditional data interfaces use iterators to programmatically
    retrieve data, Blaze preserves the ability to expose data in bulk
    form at as low a level as possible.
    """

    desctype = Enum("buffer", "buflist", "stream", "streamlist")

    #------------------------------------------------------------------------
    # Generic adapters
    #------------------------------------------------------------------------

    def asbuffer(self, copy=False):
        """ Returns the buffer as a memoryview. If **copy** is False, then the
        memoryview just references the underlying data if possible.  If
        **copy** is True, then the memoryview will always expose a new copy of
        the data.

        In the C level implementation of the DataDescriptor interface, this
        returns a void* pointer to the data.
        """
        pass

    def asbuflist(self, copy=False):
        """ Returns the contents of the buffer as a list of memoryviews.  If
        **copy** is False, then tries to return just views of data if possible.
        """

    def asstream(self):
        """ Returns a Python iterable which returns **chunksize** elements
        at a time from the buffer.  This is identical to the iterable interface
        around Buffer objects.

        If **chunksize** is greater than 1, then returns a memoryview of the
        elements if they are contiguous, or a Tuple otherwise.
        """
        pass

    def asstreamlist(self):
        """ Returns a list of Stream objects, which should be read sequentially
        (i.e. after exhausting the first stream, the second stream is read,
        etc.)
        """
        pass

class Buffer(DataDescriptor):
    """ Describes a region of memory.  Implements the memoryview interface.
    """
    
    desctype = "buffer"

    length = Int     # Total length, in bytes, of the buffer
    format = Str     # Format of each elem, in struct module syntax 
    shape = Tuple    # Numpy-style shape tuple
    strides = Tuple  # 
    readonly = Bool(False)

    # TODO: Add support for event callbacks when certain ranges are 
    # written
    #callbacks = Dict(Tuple, Function)

class Stream(DataDescriptor):
    """ Describes a data item that must be retrieved by calling a function
    to load data into memory.  Represents a scan over data.  The returned
    data is a copy and should be considered to be owned by the caller.
    """

    desctype = "stream"

    length = Int
    format = Str
    chunksize = Int(1)  # optional "optimal" number of elements to read


