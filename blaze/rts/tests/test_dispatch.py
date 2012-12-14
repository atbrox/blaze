from blaze.expr.ops import array_like
from blaze.expr.paterm import ATerm, AAppl, AInt
from blaze.rts.funcs import install, lift, lookup

from blaze import add, multiply

from unittest import skip

@skip("buggy aterm library?")
def test_match1():
    expr = AAppl(ATerm('Add'), [AInt(1), AInt(2)])
    fn, cost = lookup(expr)

    assert fn.fn == add.fn.im_func

@skip("buggy aterm library?")
def test_match2():
    expr = AAppl(ATerm('Mul'), [ATerm('Array'), ATerm('Array')])
    fn, cost = lookup(expr)

    assert fn.fn == multiply.fn.im_func

if __name__ == '__main__':
    test_match1()
    test_match2()