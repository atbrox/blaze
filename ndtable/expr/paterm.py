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

import re
from functools import partial
from collections import OrderedDict
from metadata import metadata

sep = re.compile("[\(.*\)]")

#------------------------------------------------------------------------
# Terms
#------------------------------------------------------------------------

class ATerm(object):
    def __init__(self, label):
        self.label = label

    def __str__(self):
        return str(self.label)

    def _matches(self, query):
        return self.label == query

    def __repr__(self):
        return str(self)

class AAppl(object):
    def __init__(self, spine, args):
        self.spine = spine
        self.args = args

    def _matches(self, query):
        if query == '*':
            return True

        spine, args, _ = sep.split(query)
        args = args.split(',')

        assert len(self.args) == len(args), 'Pattern argument mismatch'

        # success
        if spine.islower() or self.spine.label == spine:
            _vars = {}
            argm = [b.islower() or a._matches(b) for a,b in zip(self.args, args)]

            if spine.islower():
                _vars[spine] = self.spine

            for i, arg in enumerate(args):
                if argm[i]:
                    _vars[arg] = self.args[i]

            return _vars

        else:
            return False

    def __str__(self):
        return str(self.spine) + cat(self.args, '(', ')')

    def __repr__(self):
        return str(self)

class AAnnotation(object):
    def __init__(self, bt, ty=None, m=None):
        self.bt = bt
        self.ty = ty or None
        self.meta = set(m or [])

    @property
    def annotations(self):
        terms = map(ATerm, (self.ty,) + tuple(self.meta))
        return cat(terms, '{', '}')

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

    def _matches(self, value, meta):
        if value == '*':
            vmatch = True
        else:
            vmatch = self.bt._matches(value)

        if meta == ['*']:
            mmatch = True
        else:
            mmatch = all(a in self for a in meta)

        if vmatch and mmatch:
            return vmatch
        else:
            return False

    def __str__(self):
        if self.ty or self.meta:
            return str(self.bt) + self.annotations
        else:
            return str(self.bt)

    def __repr__(self):
        return str(self)

class AString(object):
    def __init__(self, s):
        self.s = s

    def __str__(self):
        return repr(self.s)

    def __repr__(self):
        return str(self)

class AInt(object):
    def __init__(self, n):
        self.n = n

    def __str__(self):
        return str(self.n)

    def __repr__(self):
        return str(self)

class AFloat(object):
    def __init__(self, n):
        self.n = n

    def __str__(self):
        return str(self.n)

    def __repr__(self):
        return str(self)

class AList(object):
    def __init__(self, *elts):
        self.elts = elts

    def __str__(self):
        return cat(self.elts, '[', ']')

    def __repr__(self):
        return str(self)


#------------------------------------------------------------------------
# Strategic Rewrite Combinators
#------------------------------------------------------------------------

Id = lambda s: s

def Fail():
    raise STFail()

class STFail(Exception):
    pass

compose = lambda f, g: lambda x: f(g(x))

class Fail(object):

    def __init__(self):
        pass

    def __call__(self, o):
        raise STFail()

class Choice(object):
    def __init__(self, left=None, right=None):
        self.left = left
        self.right = right
        assert left and right, 'Must provide two arguments to Choice'

    def __call__(self, s):
        try:
            return self.left(s)
        except STFail:
            return self.right(s)

class Ternary(object):
    def __init__(self, s1, s2, s3):
        self.s1 = s1
        self.s2 = s2
        self.s3 = s3

    def __call__(self, o):
        try:
            val = self.s1(o)
        except STFail:
            return self.s2(val)
        else:
            return self.s3(val)

class Fwd(object):

    def __init__(self):
        self.p = None

    def define(self, p):
        self.p = p

    def __call__(self, s):
        if self.p:
            return self.p(s)
        else:
            raise NotImplementedError('Forward declaration, not declared')

class Repeat(object):
    def __init__(self, p):
        self.p = p

    def __call__(self, s):
        val = s
        while True:
            try:
                val = self.p(val)
            except STFail:
                break
        return val

class All(object):
    def __init__(self, s):
        self.s = s

    def __call__(self, o):
        if isinstance(o, AAppl):
            return AAppl(o.spine, map(self.s, o.args))
        else:
            return o

class Some(object):
    def __init__(self, s):
        self.s = s

    def __call__(self, o):
        if isinstance(o, AAppl):
            largs = []
            for a in o.args:
                try:
                    largs.append(self.s(a))
                except STFail:
                    largs.append(a)
            return AAppl(o.spine, largs)
        else:
            raise STFail()

class Seq(object):
    def __init__(self, s1, s2):
        self.s1 = s1
        self.s2 = s2

    def __call__(self, o):
        return self.s2(self.s1(o))

class Try(object):
    def __init__(self, s):
        self.s = s

    def __call__(self, o):
        try:
            return self.s(o)
        except STFail:
            return o

class Topdown(object):
    def __init__(self, s):
        self.s = s

    def __call__(self, o):
        val = self.s(o)
        return All(self)(val)

class Bottomup(object):
    def __init__(self, s):
        self.s = s

    def __call__(self, o):
        val = All(self)(o)
        return self.s(val)

class Innermost(object):
    def __init__(self, s):
        self.s = s

    def __call__(self, o):
        return Bottomup(Try(Seq(self.s, self)))(o)

class SeqL(object):
    def __init__(self, *sx):
        self.lx = reduce(compose,sx)

    def __call__(self, o):
        return self.lx(o)

class ChoiceL(object):
    def __init__(self, *sx):
        self.sx = reduce(compose,sx)

    def __call__(self, o):
        return self.sx(o)

#------------------------------------------------------------------------
# Pattern Matching
#------------------------------------------------------------------------

def matches(pattern, term):
    """
    Collapse terms with as-patterns.
    """

    value, meta = pattern.replace(' ','').split(';')
    meta = meta.split(',')

    if isinstance(term, AAnnotation):
        return term._matches(value, meta)
    else:
        return term._matches(value)

#------------------------------------------------------------------------
# Utils
#------------------------------------------------------------------------

def cat(terms, l, r):
    """ Concatenate str representations with commas and left and right
    delimiters. """
    return l + ','.join(map(str, terms)) + r
