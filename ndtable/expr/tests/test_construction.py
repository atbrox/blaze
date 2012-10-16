from ndtable.expr.deferred import DeferredTable
from ndtable.expr.nodes import Node
from ndtable.expr.viz import view, browser, build_graph

def test_scalar_arguments():
    a = DeferredTable([1,2,3])
    children = a.node.children

    assert len(children) == 3

def test_dynamic_arguments():
    a = DeferredTable([])
    b = DeferredTable([a])

    children = b.node.children
    assert len(children) == 1

def test_dynamic_explicit():
    a = DeferredTable([])
    b = DeferredTable([a], depends=[a])

    children = b.node.children
    assert len(children) == 1

def test_simple_ops():
    a = DeferredTable([])
    b = DeferredTable([])

    c = a+b
    d = c*b

    _, graph = build_graph(d, tree=True)
    view('simple', graph)
