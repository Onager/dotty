# EFILTER Forensic Query Language
#
# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
EFILTER Abstract Syntax Tree.

The AST represents the actual canonical syntax of EFILTER, as understood by all
the behavior implementations and transformations. The string and lisp-based
syntaxes are frontends that translate into this AST, which is what is actually
interpretted.
"""

__author__ = "Adam Sindelar <adamsh@google.com>"

from efilter import protocol

from efilter.protocols import associative
from efilter.protocols import boolean
from efilter.protocols import eq
from efilter.protocols import iset
from efilter.protocols import ordered
from efilter.protocols import number
from efilter.protocols import repeated


class Expression(object):
    """Base class of the query AST.

    Behavior of the query language is encoded in the various transform
    functions. Expression themselves have no behavior, and only contain
    children and type and arity information.
    """

    __abstract = True

    children = ()
    arity = 0
    start = None
    end = None

    type_signature = (protocol.AnyType,)
    return_signature = protocol.AnyType

    def __hash__(self):
        return hash((type(self), self.children))

    def __eq__(self, other):
        return isinstance(other, type(self)) and self.children == other.children

    def __ne__(self, other):
        return not self.__eq__(other)

    def __init__(self, *children, **kwargs):
        super(Expression, self).__init__()

        self.start = kwargs.pop("start", None)
        self.end = kwargs.pop("end", None)

        if kwargs:
            raise ValueError("Unexpected argument(s) %s" % kwargs.keys())

        if self.arity and len(children) != self.arity:
            raise ValueError("%d-ary expression %s passed %d children." % (
                self.arity, type(self).__name__, len(children)))

        self.children = children

    def __repr__(self):
        if len(self.children) == 1:
            return "%s(%r)" % (type(self).__name__, self.children[0])

        lines = []
        for child in self.children:
            if isinstance(child, Expression):
                clines = [" %s" % line for line in repr(child).split("\n")]
            else:
                clines = repr(child).split("\n")
            lines.extend(clines)

        return "%s(\n%s)" % (type(self).__name__, "\n".join(lines))


class ValueExpression(Expression):
    """Unary expression."""
    arity = 1
    __abstract = True

    @property
    def value(self):
        return self.children[0]


class BinaryExpression(Expression):
    arity = 2
    __abstract = True

    @property
    def lhs(self):
        return self.children[0]

    @property
    def rhs(self):
        return self.children[1]


class VariadicExpression(Expression):
    """Represents an expression with variable arity."""

    type_signature = protocol.AnyType
    arity = None
    __abstract = True


### Value (unary) expressions ###

class Literal(ValueExpression):
    """Represents a literal, which is to say not-an-expression."""

    type_signature = None  # Depends on literal.


class Var(ValueExpression):
    """Represents a member of the evaluated object - attributes of entity."""

    type_signature = (associative.IAssociative,)


class UnaryOperation(ValueExpression):
    """Represents an operation on a single operand (subexpression)."""
    __abstract = True


class Complement(UnaryOperation):
    """Logical NOT."""

    type_signature = (boolean.IBoolean,)
    return_signature = boolean.IBoolean


class Reverse(UnaryOperation):
    """Reverse order of repeated values."""

    type_signature = (repeated.IRepeated)
    return_signature = repeated.IRepeated


### Binary expressions ###

class Pair(BinaryExpression):
    """Represents a key/value pair."""

    type_signature = (protocol.AnyType, protocol.AnyType)
    return_signature = tuple

    @property
    def key(self):
        return self.lhs

    @property
    def value(self):
        return self.rhs


class Select(BinaryExpression):
    """Represents a selection of the key (rhs) from the value (lhs).

    This is similar to using map(value, var(...)) but allows the key to
    be generated at runtime.
    """

    type_signature = (associative.IAssociative, protocol.AnyType)
    return_signature = None

    @property
    def value(self):
        return self.lhs

    @property
    def key(self):
        return self.rhs


class IsInstance(BinaryExpression):
    """Evaluates to True if the current scope is an instance of type."""


class Within(BinaryExpression):
    """Uses left side as new vars and evaluates right side as a subquery.

    Concrete behavior depends on the various subclasses, such as Filter and
    Map, but each one of them will expect left hand side to be an associative
    object holding the new vars, or a repeated variable of associative
    objects.
    """
    __abstract = True
    type_signature = (associative.IAssociative, protocol.AnyType)
    return_signature = None  # Depends on RHS.

    @property
    def context(self):
        return self.lhs

    @property
    def expression(self):
        return self.rhs


class Map(Within):
    """Returns the result of applying right side to the values on left side.

    If left is a repeated value then this will return another repeated value.
    """


class Filter(Within):
    """Filters (repeated) values on left side using expression on right side.

    Will return a repeated variable containing only the values for which the
    expression on the right evaluated to true.
    """


class Sort(Within):
    """Sorts the left hand side using the right hand side return."""


class Any(Within):
    """Returns true if the rhs evaluates as true for any value of lhs."""
    return_signature = bool


class Each(Within):
    """Returns true if the rhs evaluates as true for every value of lhs."""
    return_signature = bool


class Membership(BinaryExpression):
    """Membership of element in set."""
    type_signature = (eq.IEq, iset.ISet)
    return_signature = boolean.IBoolean

    @property
    def element(self):
        return self.lhs

    @property
    def set(self):
        return self.rhs


class RegexFilter(BinaryExpression):
    type_signature = (basestring, basestring)
    return_signature = boolean.IBoolean

    @property
    def string(self):
        return self.lhs

    @property
    def regex(self):
        return self.rhs


### Variadic Expressions ###

class Apply(VariadicExpression):
    """Represents application of arguments to a function."""
    type_signature = protocol.AnyType
    return_signature = protocol.AnyType

    @property
    def func(self):
        return self.children[0]

    @property
    def args(self):
        return self.children[1:]


class Bind(VariadicExpression):
    """Creates a new IAssociative of vars."""
    type_signature = protocol.AnyType
    return_signature = associative.IAssociative


class Repeat(VariadicExpression):
    """Creates a new IRepeated of values."""
    type_signature = protocol.AnyType
    return_signature = repeated.IRepeated


class Tuple(VariadicExpression):
    """Create a new tuple of values."""
    type_signature = protocol.AnyType
    return_signature = tuple


### Conditionals ###

class IfElse(VariadicExpression):
    """Evaluates as if-else if-else if-else blocks.

    Subexpressions are arranged as follows:

    - Children with an even ordinal number (0, 2, 4...) are conditions and
      must evaluate to an IBoolean.
    - Children with an odd ordinal number (1, 3, 5...) are the block that will
      be returned if the previous condition returned true.
    - The last child is the else block.
    """

    def conditions(self):
        """The if-else pairs."""
        for idx in xrange(1, len(self.children), 2):
            yield (self.children[idx - 1], self.children[idx])

    def default(self):
        """The else block."""
        if len(self.children) % 2:
            return self.children[-1]


### Logical Variadic ###

class LogicalOperation(VariadicExpression):
    type_signature = boolean.IBoolean
    return_signature = boolean.IBoolean
    __abstract = True


class Union(LogicalOperation):
    """Logical OR (variadic)."""


class Intersection(LogicalOperation):
    """Logical AND (variadic)."""


### Variadic Relations ###

class Relation(VariadicExpression):
    return_signature = boolean.IBoolean
    __abstract = True


class OrderedSet(Relation):
    """Abstract class to represent strict and non-strict ordering."""

    type_signature = ordered.IOrdered
    __abstract = True


class StrictOrderedSet(OrderedSet):
    """Greater than relation."""

    type_signature = ordered.IOrdered


class PartialOrderedSet(OrderedSet):
    """Great-or-equal than relation."""

    type_signature = ordered.IOrdered


class ContainmentOrder(Relation):
    """Inclusion of set 1 by set 2 and so on."""

    type_signature = iset.ISet


class Equivalence(Relation):
    """Logical == (variadic)."""

    type_signature = eq.IEq


### Variadic Arithmetic ###

class NumericExpression(VariadicExpression):
    """Arithmetic expressions."""

    return_signature = number.INumber
    __abstract = True


class Sum(NumericExpression):
    """Arithmetic + (variadic)."""

    type_signature = number.INumber


class Difference(NumericExpression):
    """Arithmetic - (variadic)."""

    type_signature = number.INumber


class Product(NumericExpression):
    """Arithmetic * (variadic)."""

    type_signature = number.INumber


class Quotient(NumericExpression):
    """Arithmetic / (variadic)."""

    type_signature = number.INumber