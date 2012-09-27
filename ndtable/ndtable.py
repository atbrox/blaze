class Index(object):
    def __init__(self, byte_interfaces):
        self.byte_interfaces = byte_interfaces
        pass

class AutoIndex(Index):
    pass

class NDTable(object):
    def __init__(self, obj, datashape, index=None, metadata=None):
        self.datashape = datashape
        self.metadata = metadata

        if isinstance(obj, list):
            self.index = AutoIndex(*obj)
        elif isinstance(obj, Index):
            self.index = index

    def __getitem__(self, index):
        pass

    def __getslice__(self, i, j):
        pass
