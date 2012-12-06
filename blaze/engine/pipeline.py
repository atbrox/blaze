# -*- coding: utf-8 -*-

"""
Defines the Pipeline class which provides a series of transformation
passes on the graph which result in code generation.
"""

from llvm.core import Module

from functools import partial
from itertools import ifilter
from collections import Counter

from blaze.plan import generate

#------------------------------------------------------------------------
# Constants
#------------------------------------------------------------------------

OP  = 0
APP = 1
VAL = 2

#------------------------------------------------------------------------
# Pipeline Combinators
#------------------------------------------------------------------------

def compose(f, g):
    return lambda *x: g(*f(*x))

#------------------------------------------------------------------------
# Pre/Post Conditions
#------------------------------------------------------------------------

#------------------------------------------------------------------------
# Passes
#------------------------------------------------------------------------
#
#                  Input
#                     |
# +----------------------+
# |          pass 1      |
# +--------|----------|--+
#        context     ast
#          |          |
#   postcondition     |
#          |          |
#   precondition      |
#          |          |
# +--------|----------|--+
# |          pass 2      |
# +--------|----------|--+
#        context     ast
#          |          |
#   postcondition     |
#                     |
#   precondition      |
#          |          |
#          |          |
# +--------|----------|--+
# |          pass 3      |
# +--------|----------|--+
#        context     ast
#          |          |
#   precondition      |
#          |          |
#          +----------+-----> Output

def do_flow(context, graph):
    context = dict(context)

    # Topologically sort the graph
    vars = topovals(graph)
    ops = topops(graph)

    # ----------------------
    context['vars'] = vars
    context['ops']  = ops
    # ----------------------

    return context, graph

def do_environment(context, graph):
    context = dict(context)

    # ----------------------
    context['llvmmodule'] = Module.new('blaze')
    context['hints'] = {}
    # ----------------------

    return context, graph

def do_convert_to_aterm(context, graph):
    "Convert the graph to an ATerm graph. See blaze/expr/paterm.py"
    context = dict(context)

    operands, plan = generate(
        context['ops'],
        context['vars'],
    )

    # ----------------------
    context['operands'] = operands
    context['output'] = plan
    # ----------------------

    return context, graph

#------------------------------------------------------------------------
# Pipeline
#------------------------------------------------------------------------

# TODO: there is no reason this should be a class, and classes
# just complicate things and encourage nasty things like
# multiple inheritance...

class Pipeline(object):
    """
    Code generation pipeline is a series of combinable Pass
    stages which thread a context and graph object through to
    produce various intermediate forms resulting in an execution
    plan.
    """
    def __init__(self, *args, **kwargs):
        self.ictx = {}

        # sequential pipeline of passes
        self.pipeline = (
            do_flow,
            do_environment,
            do_convert_to_aterm,
        )

    def run_pipeline_context(self, graph):
        """
        Run the graph through the pipeline
        """
        ictx = self.ictx

        # Fuse the passes into one functional pipeline that is the
        # sequential composition with the intermediate ``context`` and
        # ``graph`` objects threaded through.

        # pipeline = stn ∘  ... ∘  st2 ∘ st1
        pipeline = reduce(compose, self.pipeline)

        context, _ = pipeline(ictx, graph)
        return context

    def run_pipeline(self, graph):
        octx = self.run_pipeline_context(graph)
        return octx['output']

#------------------------------------------------------------------------
# Graph Manipulation
#------------------------------------------------------------------------

def khan_sort(pred, graph):
    """
    See: Kahn, Arthur B. (1962), "Topological sorting of large networks"
    """
    result = []
    count = Counter()

    for node in graph:
        for child in iter(node):
            count[child] += 1

    sort = [node for node in graph if not count[node]]

    while sort:
        node = sort.pop()
        result.append(node)

        for child in iter(node):
            count[child] -= 1
            if count[child] == 0:
                sort.append(child)

    result.reverse()

    # Collect all the nodes thats satisfy the selecter property.
    # For example, all the value nodes or all the op nodes.
    return list(ifilter(pred, result))

def tarjan_sort(pred, graph):
    raise NotImplementedError

def toposort(pred, graph, algorithm='khan'):
    """
    Sort the expression graph topologically to resolve the order needed
    to execute operations.
    """

    #
    #     +
    #    / \
    #   a   +     --> [a, b, c, d]
    #      / \
    #     b   c
    #         |
    #         d
    #

    if algorithm == 'khan':
        return khan_sort(pred, graph)
    if algorithm == 'tarjan':
        return tarjan_sort(pred, graph)
    else:
        raise NotImplementedError

topovals = partial(toposort, lambda x: x.kind == VAL)
topops   = partial(toposort, lambda x: x.kind == OP)
