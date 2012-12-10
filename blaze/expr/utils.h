#include <stdio.h>
#include <aterm2.h>

// Extract the number of subterms in a given ATerm expression.
int subterms(ATerm t) {
    Symbol sym;
    int arity;

    switch (GET_TYPE(t->header)) {
      case AT_INT:
      case AT_REAL:
      case AT_BLOB:
      case AT_APPL:
        sym = ATgetSymbol((ATermAppl) t);
        arity = ATgetArity(sym);
        return arity;
      default:
        return NULL;
    }
}

ATerm* next_subterm(ATerm t, int n) {
    switch (GET_TYPE(t->header)) {
      case AT_INT:
      case AT_REAL:
      case AT_BLOB:
      case AT_APPL:
        return ATgetArgument((ATermAppl) t, n);
      default:
        return NULL;
    }
}
