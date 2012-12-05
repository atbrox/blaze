import ast

import numpy as np

import numba
from numba import decorators
from numba.ufunc_builder import UFuncBuilder
from numba.minivect import minitypes

import blaze
import blaze.idx
from blaze.expr import visitor
from blaze.expr import ops
from blaze.expr import paterm
from blaze.engine import pipeline
from blaze.engine import executors
from blaze.sources import canonical

from blaze.datashape import datashape
from blaze import Table, NDTable, Array, NDArray

from numbapro.vectorize import Vectorize

class GraphToAst(visitor.ExprVisitor):
    """
    Convert a blaze graph to a Python AST.
    """

    binop_to_astop = {
        ops.Add: ast.Add,
        ops.Mul: ast.Mult,
    }

    def __init__(self):
        super(GraphToAst, self).__init__()
        self.ufunc_builder = UFuncBuilder()

    def App(self, app):
        if app.operator.arity == 2:
            op = binop_to_astop.get(type(app.operator), None)
            if op is not None:
                left, right = self.visit(app.operator.children)
                return ast.BinOp(left=left, op=op(), right=right)

        return self.Unknown(app)

    def Unknown(self, tree):
        return self.ufunc_builder.register_operand(tree)


def build_executor(pyast_function, operands):
    "Build a ufunc and an wrapping executor from a Python AST"
    vectorizer = Vectorize(pyast_function)
    vectorizer.add(*[minitype(op) for op in operands])
    ufunc = vectorizer.build_ufunc()

    operands_dtypes = map(get_dtype, operands)
    # TODO: this should be part of the blaze graph
    result_dtype = reduce(np.promote_types, operands_dtypes)

    # TODO: build an executor tree and substitute where we can evaluate
    executor = executors.ElementwiseLLVMExecutor(
        ufunc, operands_dtypes, result_dtype)

    return executor

class ATermToAst(visitor.BasicGraphVisitor):
    """
    Convert an aterm graph to a Python AST.
    """

    opname_to_astop = {
        'add': ast.Add,
        'mul': ast.Mult,
    }

    nesting_level = 0

    def __init__(self):
        super(ATermToAst, self).__init__()
        self.ufunc_builder = UFuncBuilder()

    def set_executor(self, aterm, executor_id):
        aterm

    def register(self, result):
        if self.nesting_level == 0:
            # Bottom of graph that we can handle
            operands = self.ufunc_builder.operands
            pyast_function = self.ufunc_builder.build_ufunc_ast(pyast)
            executor = build_executor(pyast_function, operands)


    def AAppl(self, app):
        "Look for unops, binops and reductions we can handle"
        if paterm.matches('Arithmetic;*', app.spine):
            opname = app.args[0].lower()
            op = self.opname_to_astop.get(opname, None)
            args = app.args[1:]
            if op is not None and len(args) == 2:
                self.nesting_level += 1
                left, right = self.visit(args)
                self.nesting_level -= 1

                result = ast.BinOp(left=left, op=op(), right=right)
                return self.register(result)

        return self.unhandled(app)

    def AInt(self, constant):
        return ast.Num(n=constant.n)

    AFloat = AInt

    def unhandled(self, aterm, children=()):
        "An term we can't handle, scan for sub-trees"
        nesting_level = self.nesting_level
        state = self.ufunc_builder.save()

        self.nesting_level = 0
        self.visit(childrem)
        self.nesting_level = nesting_level
        self.ufunc_builder.restore(state)

        if self.nesting_level:
            self.ufunc_builder.register_operand(tree)

        return aterm


def getsource(ast):
    from meta import asttools
    return asttools.dump_python_source(ast).strip()

def get_dtype(blaze_obj):
    # This is probably wrong...
    return blaze_obj.datashape.operands[-1].to_dtype()

def minitype(blaze_obj):
    """
    Get the numba/minivect type from a blaze object (NDArray or whatnot).
    This should be a direct mapping. Even better would be to unify the two
    typesystems...
    """
    dtype = get_dtype(blaze_obj)
    return minitypes.map_dtype(dtype)

#def convert_graph(lazy_blaze_graph):
#    """
#    >>> a = NDArray([1, 2, 3, 4], datashape('2, 2, int'))
#    >>> operands, ast_func = convert_graph(a + a)
#
#    >>> print getsource(ast_func)
#    def ufunc0(op0, op1):
#        return (op0 + op1)
#    >>> print operands
#    [Array(4346842064){True}, Array(4346842064){True}]
#    """
#    # Convert blaze graph to ATerm graph
#    p = pipeline.Pipeline()
#    context = p.run_pipeline_context(lazy_blaze_graph)
#
#    # Convert to ast
#    aterm_operands, pyast_function = convert_aterm(context, context['output'])
#
#    global_id = lambda aterm: aterm.bt.args[0]
#    operands = [operands[global_id(aterm_op)] for aterm_op in aterm_operands]
#
#    return operands, pyast_function

def convert_aterm(context, aterm_graph):
    """
    Convert an aterm graph to a Python AST.
    """
    visitor = ATermToAst()
    pyast = visitor.visit(aterm_graph)
    operands = visitor.ufunc_builder.operands
    pyast_function = visitor.ufunc_builder.build_ufunc_ast(pyast)
    return operands, pyast_function

def substitute_llvm_executors(aterm_graph):
    """
    >>> execute_graph(a + a)
    """
    operands, pyast_function = convert_graph(lazy_blaze_graph)


if __name__ == '__main__':
    a = NDArray([1, 2, 3, 4], datashape('2, 2, int'))
    ops, funcdef = convert_graph(a + a)
#    print getsource(funcdef)
#    print result

#    import doctest
#    doctest.testmod()
