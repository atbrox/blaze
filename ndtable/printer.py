# TODO: Talk with Francesc he has a robust array printer in
# carray we can use.

from pprint import pformat

def generic_repr(name, obj, deferred):
    """
    Generic pretty printer for NDTable and NDArray
    """
    header = "%s(%s)\n" % (name, obj.datashape)
    header += "  values   := %s;\n" % list(obj.backends)
    header += "  metadata := %s;\n" % (pformat(obj.metadata, width=1))

    # Do we force str() to render and consequently do a read
    # operation?
    if deferred:
        fullrepr = header + '<Lazy>'
    else:
        fullrepr = header + str(obj)

    return fullrepr

#------------------------------------------------------------------------
# Console
#------------------------------------------------------------------------

def array2string(a):
    return ''

def table2string(t):
    return ''

#------------------------------------------------------------------------
# IPython Notebook
#------------------------------------------------------------------------

def array2html(a):
    html = "<table></table>"

    return ('<div style="max-height:1000px;'
            'max-width:1500px;overflow:auto;">\n' +
            html + '\n</div>')

def table2html(t):
    html = "<table></table>"

    return ('<div style="max-height:1000px;'
            'max-width:1500px;overflow:auto;">\n' +
            html + '\n</div>')
