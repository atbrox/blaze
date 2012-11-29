"""
Extended ATerm grammar which distinguishes between different
annotation formats:

    - type
    - metadata
    - metacompute

Still a strict subset of ATerm so it can be parsed and
manipulated by Stratego rewriters.

::

    t : bt                 -- basic term
      | bt {ty,m1,...}     -- annotated term

    bt : C                 -- constant
       | C(t1,...,tn)      -- n-ary constructor
       | [t1,...,tn]       -- list
       | "ccc"             -- quoted string
       | int               -- integer
       | real              -- floating point number

"""

from collections import OrderedDict
from metadata import metadata

#------------------------------------------------------------------------
# Terms
#------------------------------------------------------------------------

class ATerm(object):
    def __init__(self, label):
        self.label = label

    def __str__(self):
        return str(self.label)

class AAppl(object):
    def __init__(self, spine, args):
        self.spine = spine
        self.args = args

    def __str__(self):
        return str(self.spine) + cat(self.args, '(', ')')

class AAnnotation(object):
    def __init__(self, bt, ty=None, m=None):
        self.bt = bt
        self.ty = ty or None
        self.meta = m or ()

    @property
    def annotations(self):
        terms = map(ATerm, self.meta)
        return AList(*terms)

    def __contains__(self, key):
        if key == 'type':
            return True
        else:
            return key in self.meta

    def __getitem__(self, key):
        if key == 'type':
            return self.ty
        else:
            return key in self.meta

    def matches(self, query):
        value, meta = query.replace(' ','').split(';')
        meta = meta.split(',')

        if value == '*':
            vmatch = True
        else:
            vmatch = self.bt == query

        if meta == '*':
            mmatch = True
        else:
            mmatch = [a in self for a in meta]

        return vmatch and all(mmatch)

    def __str__(self):
        return str(self.bt) + '{' + str(self.annotations) + '}'

class AString(object):
    def __init__(self, s):
        self.s = s

    def __str__(self):
        return repr(self.s)

class AInt(object):
    def __init__(self, n):
        self.n = n

    def __str__(self):
        return str(self.n)

class AFloat(object):
    def __init__(self, n):
        self.n = n

    def __str__(self):
        return str(self.n)

class AList(object):
    def __init__(self, *elts):
        self.elts = elts

    def __str__(self):
        return cat(self.elts, '[', ']')

#------------------------------------------------------------------------
# Utils
#------------------------------------------------------------------------

def cat(terms, l, r):
    return l + ','.join(map(str, terms)) + r

if __name__ == '__main__':
    a = ATerm('a')
    b = ATerm('b')
    lst =  AList(a,b)
    annot = ('contig', 'fizzy', 'b')
    aterm = AAnnotation(lst, int, annot)

    print aterm['type']
    print aterm['a']
    print aterm['type']
    print aterm['foobar']
    print aterm.matches('*;fizzy,b')
    print aterm
