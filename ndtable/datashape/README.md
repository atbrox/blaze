Datashapes
==========

Datashape is a generalization of dtype and shape into a micro
type system which lets us describe the high-level structure of
NDTable and IndexArray objects.

There are primitive machine types which on top of you can build
composite and dimensionalized structures.

```python
int32
float
```

Fixed Dimensions
----------------

Fixed dimensions are just integer values at the top level of the
datatype.

```python
2, int32
```

Is an length 2 array.

```python
array([1, 2])
```

A 2 by 3 matrix matrix has datashape:


```python
2, 3, int32
```

```python
array([[ 1,  2,  3],
       [ 4,  5,  6]])
```

Constructors
------------

A type constructor is higher type that produces new named types from
arguments given. These are called **alias** types, they don't add any
additional structure they just provide a new name.

```python
Dim2       = N, M
Quaternion = 4, 4, int32
```

Record Types
------------

Record types are struct-like objects which hold a collection
of types keyed by labels. For example a pixel.

```python
RGBA = {r: int32, g: int32, b: int32, a: int8}
```

Enumeration Types
-----------------

An enumeration provides a dimension which is specified by

```python
Lengths = {1,2,3}
```

```python
Lengths * 3
```

This would correspond to a variable ragged triangular table of
the form:

```
           3

         * * *
Lengths    * *
             *
```

Variable Length
---------------

Variable length types correspond where the dimension is not
known.

```python
ShortStrings = Var(0, 5)*char
```

For example ```5*ShortStrings``` might be a table of the form.

```python
foo
bar
fizz
bang
pop
```

Compounded variable lengths are **ragged tables**.

```python
Var(0,5), Var(0,5), int32
```

Would permit tables of the form:

```
1 2 3 7 1
  4 5 8 1
  3 1 9
    1
```

```
1 3 7
1 2  
1
```

Stream Types
------------

A stream is a special case of ``Var`` where the upper bound is
infinity. It signifies a potentially infinite stream of elements.
```Stream(RGBA)``` might be stream of values from a photosensor. Where
each row represents a measurement at a given time.

```python
{ 101 , 202 , 11  , 32 }
{ 50  , 255 , 11  , 0 }
{ 96  , 100 , 110 , 0 }
{ 96  , 50  , 60  , 0 }
```

Nullable Types
--------------

A value that or may not be null is encoded as a ``Either``
constructor.

```python
MaybeFloat = Either float nan
MaybeInt   = Either int32 nan
```

Or for union ( in the C-sense) like structures.

```python
IntOrChar   = Either int32 char
```

Function Types
--------------

** Work in Progress **

Function types are dimension specifiers that are encoded by
arbitrary logic. We only specify their argument types are
return types at the type level. The ``(->)`` is used to specify
the lambda expression.

For example a two dimensional table where an extra dimension is
added whose length is a range between the sizes of the first two.

```python
A, B, ( A, B -> Var(A, B) ), int32 
```

Pointer Types
-------------

Pointers are dimension specifiers like machine types but where
the data is not in specified by value, but *by reference*. We use
adopt same notation as LLVM.

Pointer to a integer in local memory:

```python
int32*
```

Pointer to a 4x4 matrix of integers in local memory

```python
(4, 4, int32)*
```

Pointer to a record in local memory

```python
{x: int32, y:int32, label: string}*
```

Pointer to integer in a shared memory segement keyed by 'foo'

```python
int32 (shm 'foo')*
```

Pointer to integer on a array server 'bar'

```python
int32 (rmt array://bar)*
```

Parametric Types
----------------

** Work in Progress **

The natural evolution is to support parametric types.

Which lets us have type constructors with free variables on the
left side of the constructor.

```python
# Constructor
Point T = {x: T, y: T}

# Concrete instance
Point int32 = {x: int32, y: int32}
```

Then can be treated atomically as a ``Point(int32)`` in programming
logic while the underlying machinery is able to substitute in the
right side object when dealing with concrete values.

For example, high dimensional matrix types:

```python
ctensor4 A B C D = A, B, C, D, complex64
```

```python
x = ctensor4 A B C D

rank x     = 4
outerdim x = A
innerdim x = D
```

And with a bit more machinery  allow parametric polymorphism.

```python
product :: (ctensor a b X) -> (ctensor X c d) -> (ctensor a b c d)
product a b = numpy.outer(a,b)
```
