"""
Defines the Pipeline class which provides a series of transformation
passes on the graph which result in code generation.
"""

from collections import Counter

def compose(f, g):
    return lambda *x: f(*g(*x))

#------------------------------------------------------------------------
# Passes
#------------------------------------------------------------------------

def do_flow(context, graph):
    context = dict(context)

    sort = toposort(graph)
    context['order'] = sort

    return context, graph

def do_environment(context, graph):
    context = dict(context)
    context['env'] = {}

    return context, graph

def do_codegen(context, graph):
    context = dict(context)

    context['output'] = None
    return context, graph

def do_symbolic_optimizer(context, graph):
    context = dict(context)
    sort = toposort(graph)

    return context, graph

#------------------------------------------------------------------------
# Pipeline
#------------------------------------------------------------------------

class Pipeline(object):
    """
    Code generation pipeline is a series of combinable Pass
    stages which thread a context and graph object through to
    produce various intermediate forms.
    """
    def __init__(self):
        self.ictx = {}

        # sequential pipeline of passes
        self.pipeline = (
            do_flow,
            do_environment,
            do_codegen,
        )

    def run_pipeline(self, graph):
        ictx = self.ictx
        octx, _ = reduce(compose, self.pipeline)(ictx, graph)
        return octx['output']

def toposort(graph):
    """
    Sort the expression graph topologically to resolve the order needed
    to execute operations.
    """

    result = []
    count = Counter()

    for node in iter(graph):
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
    return result
