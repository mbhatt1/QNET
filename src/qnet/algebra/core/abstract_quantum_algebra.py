"""Common algebra of "quantum" objects

Quantum objects have an associated Hilbert space, and they (at least partially)
summation, products, multiplication with a scalar, and adjoints.

The algebra defined in this module is the superset of the Hilbert space algebra
of states (augmented by the tensor product), and the C* algebras of operators
and superoperators.
"""
import re
from abc import ABCMeta, abstractmethod
from itertools import product as cartesian_product

import sympy
from sympy import Symbol, sympify

from .hilbert_space_algebra import ProductSpace, LocalSpace, TrivialSpace
from .abstract_algebra import Operation, Expression, substitute
from .indexed_operations import IndexedSum
from ...utils.ordering import (
    DisjunctCommutativeHSOrder, FullCommutativeHSOrder, KeyTuple, )
from ...utils.indices import (
    SymbolicLabelBase, IndexOverList, IndexOverFockSpace, IndexOverRange)


__all__ = [
    'ScalarTimesQuantumExpression', 'QuantumExpression', 'QuantumOperation',
    'QuantumPlus', 'QuantumTimes', 'SingleQuantumOperation', 'QuantumAdjoint',
    'QuantumSymbol', 'QuantumIndexedSum', 'Sum']
__private__ = [
    'ensure_local_space']


_sympyOne = sympify(1)


class QuantumExpression(Expression, metaclass=ABCMeta):
    """Common base class for any expression that is associated with a Hilbert
    space"""

    _zero = None  # The neutral element for addition
    _one = None  # The neutral element for multiplication
    _base_cls = None  # The most general class we can add / multiply
    _scalar_times_expr_cls = None   # class for multiplication with scalar
    _plus_cls = None  # class for internal addition
    _times_cls = None  # class for internal multiplication
    _adjoint_cls = None  # class for the adjoint
    _indexed_sum_cls = None  # class for indexed sum

    _order_index = 0  # index of "order group": things that should go together
    _order_coeff = 1  # scalar prefactor
    _order_name = None

    def __init__(self, *args, **kwargs):
        self._order_args = KeyTuple([
            arg._order_key if hasattr(arg, '_order_key') else arg
            for arg in args])
        self._order_kwargs = KeyTuple([
            KeyTuple([
                key, val._order_key if hasattr(val, '_order_key') else val])
            for (key, val) in sorted(kwargs.items())])
        super().__init__(*args, **kwargs)

    @property
    def is_zero(self):
        """Check whether the expression is equal to zero.

        Specifically, this checks whether the expression is equal to the
        neutral element for the addition within the algebra. This does not
        generally imply equality with a scalar zero:

        >>> ZeroOperator.is_zero
        True
        >>> ZeroOperator == 0
        False
        """
        return self == self._zero

    @property
    def _order_key(self):
        return KeyTuple([
            self._order_index, self._order_name or self.__class__.__name__,
            self._order_coeff, self._order_args, self._order_kwargs])

    @property
    @abstractmethod
    def space(self):
        """The :class:`.HilbertSpace` on which the operator acts
        non-trivially"""
        raise NotImplementedError(self.__class__.__name__)

    def adjoint(self):
        """The Hermitian adjoint of the Expression"""
        return self._adjoint()

    def dag(self):
        """Alias for :meth:`adjoint`"""
        return self._adjoint()

    def conjugate(self):
        """Alias for :meth:`adjoint`"""
        return self._adjoint()

    @abstractmethod
    def _adjoint(self):
        raise NotImplementedError(self.__class__.__name__)

    def expand(self):
        """Expand out distributively all products of sums.

        Note:
            This does not expand out sums of scalar coefficients. You may use
            :meth:`simplify_scalar` for this purpose.
        """
        return self._expand()

    def _expand(self):
        return self

    def simplify_scalar(self, func=sympy.simplify):
        """Simplify all scalar symbolic (SymPy) coefficients by appyling `func`
        to them"""
        return self._simplify_scalar(func=func)

    def _simplify_scalar(self, func):
        return self

    def diff(self, sym: Symbol, n: int = 1, expand_simplify: bool = True):
        """Differentiate by scalar parameter `sym`.

        Args:
            sym: What to differentiate by.
            n: How often to differentiate
            expand_simplify: Whether to simplify the result.

        Returns:
            The n-th derivative.
        """
        if sym.free_symbols.issubset(self.free_symbols):
            expr = self
            for k in range(n):
                expr = expr._diff(sym)
            if expand_simplify:
                expr = expr.expand().simplify_scalar()
            return expr
        else:
            return self.__class__._zero

    def _diff(self, sym):
        # TODO: abstract_method
        raise NotImplementedError()

    def series_expand(
            self, param: Symbol, about, order: int) -> tuple:
        r"""Expand the expression as a truncated power series in a
        scalar parameter.

        When expanding an expr for a parameter $x$ about the point $x_0$ up to
        order $N$, the resulting coefficients $(c_1, \dots, c_N)$ fulfill

        .. math::

            \text{expr} = \sum_{n=0}^{N} c_n (x - x_0)^n + O(N+1)

        Args:
            param: Expansion parameter $x$
            about (Scalar): Point $x_0$ about which to expand
            order: Maximum order $N$ of expansion (>= 0)

        Returns:
            tuple of length ``order + 1``, where the entries are the
            expansion coefficients, $(c_0, \dots, c_N)$.

        Note:
            The expansion coefficients are
            "type-stable", in that they share a common base class with the
            original expression. In particular, this applies to "zero"
            coefficients::

                >>> expr = KetSymbol("Psi", hs=0)
                >>> t = sympy.symbols("t")
                >>> assert expr.series_expand(t, 0, 1) == (expr, ZeroKet)
        """
        expansion = self._series_expand(param, about, order)
        # _series_expand is generally not "type-stable", so we continue to
        # ensure the type-stability
        res = []
        for v in expansion:
            if v == 0 or v.is_zero:
                v = self._zero
            elif v == 1:
                v = self._one
            assert isinstance(v, self._base_cls)
            res.append(v)
        return tuple(res)

    def _series_expand(self, param, about, order):
        # Expressions are assumed constant by default.
        from qnet.algebra.core.scalar_algebra import Zero
        return (self,) + ((Zero,) * order)

    def __add__(self, other):
        if not isinstance(other, self._base_cls):
            try:
                other = self.__class__._one * other
            except TypeError:
                pass
        if isinstance(other, self.__class__._base_cls):
            return self.__class__._plus_cls.create(self, other)
        else:
            return NotImplemented

    def __radd__(self, other):
        # addition is assumed to be commutative
        return self.__add__(other)

    def __mul__(self, other):
        from qnet.algebra.core.scalar_algebra import is_scalar, ScalarValue
        if not isinstance(other, self._base_cls):
            if is_scalar(other):
                other = ScalarValue.create(other)
                # if other was an ScalarExpression, the conversion above leaves
                # it unchanged
                return self.__class__._scalar_times_expr_cls.create(
                    other, self)
        if isinstance(other, self.__class__._base_cls):
            return self.__class__._times_cls.create(self, other)
        else:
            return NotImplemented

    def __rmul__(self, other):
        # multiplication with scalar is assumed to be commutative, but any
        # other multiplication is not
        from qnet.algebra.core.scalar_algebra import is_scalar
        if is_scalar(other):
            return self.__mul__(other)
        else:
            return NotImplemented

    def __sub__(self, other):
        return self + (-1) * other

    def __rsub__(self, other):
        return (-1) * self + other

    def __neg__(self):
        return (-1) * self

    def __truediv__(self, other):
        try:
            factor = _sympyOne / other
            return self * factor
        except TypeError:
            try:
                return super().__rmul__(other)
            except AttributeError:
                return NotImplemented

    def __pow__(self, other):
        if other == 0:
            return self._one
        elif other == 1:
            return self
        else:
            try:
                other_is_int = (other == int(other))
            except TypeError:
                other_is_int = False
            if other_is_int:
                if other > 1:
                    return self.__class__._times_cls.create(
                        *[self for _ in range(other)])
                elif other < 1:
                    return 1 / self**(-other)
                else:
                    raise ValueError("Invalid exponent %r" % other)
            else:
                return NotImplemented


class QuantumSymbol(QuantumExpression, metaclass=ABCMeta):
    """A symbolic constant"""
    _rx_label = re.compile('^[A-Za-z][A-Za-z0-9]*(_[A-Za-z0-9().+-]+)?$')

    def __init__(self, label, *, hs):
        self._label = label
        if isinstance(label, str):
            if not self._rx_label.match(label):
                raise ValueError(
                    "label '%s' does not match pattern '%s'"
                    % (label, self._rx_label.pattern))
        elif isinstance(label, SymbolicLabelBase):
            self._label = label
        else:
            raise TypeError(
                "type of label must be str or SymbolicLabelBase, not %s"
                % type(label))
        if isinstance(hs, (str, int)):
            hs = LocalSpace(hs)
        elif isinstance(hs, tuple):
            hs = ProductSpace.create(*[LocalSpace(h) for h in hs])
        self._hs = hs
        super().__init__(label, hs=hs)

    @property
    def label(self):
        return self._label

    @property
    def args(self):
        return (self.label, )

    @property
    def kwargs(self):
        return {'hs': self._hs}

    @property
    def space(self):
        return self._hs

    def _expand(self):
        return self

    @property
    def free_symbols(self):
        try:
            return self.label.free_symbols
        except AttributeError:
            return set()

    def _adjoint(self):
        return self.__class__._adjoint_cls(self)


class QuantumOperation(QuantumExpression, Operation, metaclass=ABCMeta):
    """Base class for operations on quantum expressions within the same
    fundamental set"""

    # "same fundamental set" means all operandas are instances of _base_cls
    # Operations that involve objects from different sets should directly
    # subclass from QuantumExpression and Operation

    _order_index = 1  # Operations are printed after "atomic" Expressions

    def __init__(self, *operands, **kwargs):
        for o in operands:
            assert isinstance(o, self.__class__._base_cls)
        op_spaces = [o.space for o in operands]
        self._space = ProductSpace.create(*op_spaces)
        super().__init__(*operands, **kwargs)

    @property
    def space(self):
        """Hilbert space of the operation result"""
        return self._space

    def _simplify_scalar(self, func):
        simplified_operands = []
        operands_have_changed = False
        for op in self.operands:
            new_op = op.simplify_scalar(func=func)
            simplified_operands.append(new_op)
            if new_op is not op:
                operands_have_changed = True
        if operands_have_changed:
            return self.create(*simplified_operands, **self.kwargs)
        else:
            return self


class SingleQuantumOperation(QuantumOperation, metaclass=ABCMeta):
    """Base class for operations on a single quantum expression"""

    def __init__(self, op, **kwargs):
        if not isinstance(op, self._base_cls):
            try:
                op = op * self.__class__._one
            except TypeError:
                pass
        super().__init__(op, **kwargs)

    @property
    def operand(self):
        """The operator that the operation acts on"""
        return self.operands[0]

    def _series_expand(self, param, about, order):
        ope = self.operand.series_expand(param, about, order)
        return tuple(opet.adjoint() for opet in ope)


class QuantumAdjoint(SingleQuantumOperation, metaclass=ABCMeta):
    """Base class for adjoints of quantum expressions"""

    def _expand(self):
        eo = self.operand.expand()
        if isinstance(eo, self.__class__._plus_cls):
            summands = [eoo.adjoin() for eoo in eo.operands]
            return self.__class__._plus_cls.create(*summands)
        return eo.adjoint()

    def _diff(self, sym):
        return self.__class__.create(self.operands[0].diff(sym))

    def _adjoint(self):
        return self.operand


class QuantumPlus(QuantumOperation, metaclass=ABCMeta):
    """General implementation of addition of quantum expressions"""
    order_key = FullCommutativeHSOrder
    _neutral_element = None

    def __init__(self, *operands, **kwargs):
        if len(operands) <= 1:
            raise TypeError(
                "%s requires at least two operands" % self.__class__.__name__)
        super().__init__(*operands, **kwargs)

    def _expand(self):
        summands = [o.expand() for o in self.operands]
        return self.__class__._plus_cls.create(*summands)

    def _series_expand(self, param, about, order):
        tuples = (o.series_expand(param, about, order) for o in self.operands)
        res = (self.__class__._plus_cls.create(*tels) for tels in zip(*tuples))
        return res

    def _diff(self, sym):
        return sum([o.diff(sym) for o in self.operands], self.__class__._zero)

    def _adjoint(self):
        return self.__class__._plus_cls(*[o.adjoint() for o in self.operands])


class QuantumTimes(QuantumOperation, metaclass=ABCMeta):
    """General implementation of product of quantum expressions"""
    order_key = DisjunctCommutativeHSOrder
    _neutral_element = None

    def __init__(self, *operands, **kwargs):
        if len(operands) <= 1:
            raise TypeError(
                "%s requires at least two operands" % self.__class__.__name__)
        super().__init__(*operands, **kwargs)

    def factor_for_space(self, spc):
        """Return a tuple of two products, where the first product contains the
        given Hilbert space, and the second product is disjunct from it."""
        if spc == TrivialSpace:
            ops_on_spc = [
                o for o in self.operands if o.space is TrivialSpace]
            ops_not_on_spc = [
                o for o in self.operands if o.space > TrivialSpace]
        else:
            ops_on_spc = [
                o for o in self.operands if (o.space & spc) > TrivialSpace]
            ops_not_on_spc = [
                o for o in self.operands if (o.space & spc) is TrivialSpace]
        return (
            self.__class__._times_cls.create(*ops_on_spc),
            self.__class__._times_cls.create(*ops_not_on_spc))

    def _expand(self):
        eops = [o.expand() for o in self.operands]
        # store tuples of summands of all expanded factors
        eopssummands = [
            eo.operands if isinstance(eo, self.__class__._plus_cls) else (eo,)
            for eo in eops]
        # iterate over a cartesian product of all factor summands, form product
        # of each tuple and sum over result
        summands = []
        for combo in cartesian_product(*eopssummands):
            summand = self.__class__._times_cls.create(*combo)
            summands.append(summand)
        ret = self.__class__._plus_cls.create(*summands)
        if isinstance(ret, self.__class__._plus_cls):
            return ret.expand()
        else:
            return ret

    def _series_expand(self, param, about, order):
        assert len(self.operands) > 1
        cfirst = self.operands[0].series_expand(param, about, order)
        if len(self.operands) > 2:
            crest = (
                self.__class__(*self.operands[1:])
                .series_expand(param, about, order))
        else:
            # a single remaining operand needs to be treated explicitly because
            # we didn't use `create` for the `crest` above, for efficiency
            crest = self.operands[1].series_expand(param, about, order)
        return _series_expand_combine_prod(cfirst, crest, order)

    def _diff(self, sym):
        assert len(self.operands) > 1
        first = self.operands[0]
        rest = self.__class__._times_cls.create(*self.operands[1:])
        return first.diff(sym) * rest + first * rest.diff(sym)

    def _adjoint(self):
        return self.__class__._times_cls.create(
                *[o.adjoint() for o in reversed(self.operands)])


class ScalarTimesQuantumExpression(
        QuantumExpression, Operation, metaclass=ABCMeta):
    """Product of a scalar and an expression"""

    @classmethod
    def create(cls, coeff, term):
        from qnet.algebra.core.scalar_algebra import Scalar, ScalarValue
        if not isinstance(coeff, Scalar):
            coeff = ScalarValue.create(coeff)
        return super().create(coeff, term)

    def __init__(self, coeff, term):
        from qnet.algebra.core.scalar_algebra import Scalar, ScalarValue
        if not isinstance(coeff, Scalar):
            coeff = ScalarValue.create(coeff)
        self._order_coeff = coeff
        self._order_args = KeyTuple([term._order_key])
        super().__init__(coeff, term)

    @property
    def coeff(self):
        return self.operands[0]

    @property
    def term(self):
        return self.operands[1]

    def _substitute(self, var_map, safe=False):
        st = self.term.substitute(var_map)
        if isinstance(self.coeff, sympy.Basic):
            svar_map = {k: v for k, v in var_map.items()
                        if not isinstance(k, Expression)}
            sc = self.coeff.subs(svar_map)
        else:
            sc = substitute(self.coeff, var_map)
        if safe:
            return self.__class__(sc, st)
        else:
            return sc * st

    @property
    def free_symbols(self):
        return self.coeff.free_symbols | self.term.free_symbols

    def _adjoint(self):
        return self.coeff.conjugate() * self.term.adjoint()

    @property
    def _order_key(self):
        from qnet.printing.asciiprinter import QnetAsciiDefaultPrinter
        ascii = QnetAsciiDefaultPrinter().doprint
        t = self.term._order_key
        try:
            c = abs(float(self.coeff))  # smallest coefficients first
        except (ValueError, TypeError):
            c = float('inf')
        return KeyTuple(t[:2] + (c,) + t[3:] + (ascii(self.coeff),))

    @property
    def space(self):
        return self.operands[1].space

    def _expand(self):
        c, t = self.operands
        et = t.expand()
        if isinstance(et, self.__class__._plus_cls):
            summands = [c * eto for eto in et.operands]
            return self.__class__._plus_cls.create(*summands)
        return c * et

    def _series_expand(self, param, about, order):
        ce = self.coeff.series_expand(param, about, order)
        te = self.term.series_expand(param, about, order)
        return _series_expand_combine_prod(ce, te, order)

    def _diff(self, sym):
        c, t = self.operands
        return c.diff(sym) * t + c * t.diff(sym)

    def _simplify_scalar(self, func):
        coeff, term = self.operands
        try:
            if isinstance(coeff.val, sympy.Basic):
                coeff = func(coeff)
        except AttributeError:
            # coeff is not a SymPy ScalarValue; leave it unchanged
            pass
        return coeff * term.simplify_scalar(func=func)

    def __complex__(self):
        if self.term is self.__class__._one:
            return complex(self.coeff)
        return NotImplemented

    def __float__(self):
        if self.term is self.__class__._one:
            return float(self.coeff)
        return NotImplemented


class QuantumIndexedSum(IndexedSum, SingleQuantumOperation, metaclass=ABCMeta):

    @property
    def space(self):
        """The Hilbert space of the sum's term"""
        return self.term.space

    def _expand(self):
        return self.__class__.create(self.term.expand(), *self.ranges)

    def _series_expand(self, param, about, order):
        raise NotImplementedError()

    def _adjoint(self):
        return self.__class__.create(self.term.adjoint(), *self.ranges)

    def __mul__(self, other):
        from qnet.algebra.core.scalar_algebra import is_scalar
        if isinstance(other, IndexedSum):
            other = other.make_disjunct_indices(self)
            new_ranges = self.ranges + other.ranges
            new_term = self.term * other.term
            # note that class may change, depending on type of new_term
            return new_term.__class__._indexed_sum_cls.create(
                new_term, *new_ranges)
        elif is_scalar(other):
            return self._class__._scalar_times_expr_cls(other, self)
        elif isinstance(other, ScalarTimesQuantumExpression):
            return self._class__._scalar_times_expr_cls(
                other.coeff, self * other.term)
        else:
            sum = self.make_disjunct_indices(*other.bound_symbols)
            new_term = sum.term * other
            return new_term.__class__._indexed_sum_cls.create(
                new_term, *sum.ranges)

    def __rmul__(self, other):
        from qnet.algebra.core.scalar_algebra import is_scalar
        if isinstance(other, IndexedSum):
            self_new = self.make_disjunct_indices(other)
            new_ranges = other.ranges + self_new.ranges
            new_term = other.term * self_new.term
            # note that class may change, depending on type of new_term
            return new_term.__class__._indexed_sum_cls.create(
                new_term, *new_ranges)
        elif is_scalar(other):
            return self.__class__._scalar_times_expr_cls(other, self)
        elif isinstance(other, ScalarTimesQuantumExpression):
            return self._class__._scalar_times_expr_cls(
                other.coeff, other.term * self)
        else:
            sum = self.make_disjunct_indices(*other.bound_symbols)
            new_term = other * sum.term
            return new_term.__class__._indexed_sum_cls.create(
                new_term, *sum.ranges)

    def __add__(self, other):
        raise NotImplementedError()

    def __radd__(self, other):
        raise NotImplementedError()

    def __sub__(self, other):
        raise NotImplementedError()

    def __rsub__(self, other):
        raise NotImplementedError()


def _sum_over_list(term, idx, values):
    return IndexOverList(idx, values)


def _sum_over_range(term, idx, start_from, to, step=1):
    return IndexOverRange(idx, start_from=start_from, to=to, step=step)


def _sum_over_fockspace(term, idx, hs=None):
    if hs is None:
        return IndexOverFockSpace(idx, hs=term.space)
    else:
        return IndexOverFockSpace(idx, hs=hs)


def Sum(idx, *args, **kwargs):
    """Instantiator for an arbitrary indexed sum.

    This returns a function that instantiates the appropriate
    :class:`QuantumIndexedSum` subclass for a given term expression. It is the
    preferred way to "manually" create indexed sum expressions, closely
    resembling the normal mathematical notation for sums.

    Args:
        idx (IdxSym): The index symbol over which the sum runs
        args: arguments that describe the values over which `idx` runs,
        kwargs: keyword-arguments, used in addition to `args`

    Returns:
        callable: an instantiator function that takes a
        arbitrary `term` that should generally contain the `idx` symbol, and
        returns an indexed sum over that `term` with the index range specified
        by the original `args` and `kwargs`.

    There is considerable flexibility to specify concise `args` for a variety
    of index ranges.

    Assume the following setup::

        >>> i = IdxSym('i'); j = IdxSym('j')
        >>> ket_i = BasisKet(FockIndex(i), hs=0)
        >>> ket_j = BasisKet(FockIndex(j), hs=0)
        >>> hs0 = LocalSpace('0')

    Giving `i` as the only argument will sum over the indices of the basis
    states of the Hilbert space of `term`::

        >>> s = Sum(i)(ket_i)
        >>> unicode(s)
        '∑_{i ∈ ℌ₀} |i⟩⁽⁰⁾'

    You may also specify a Hilbert space manually::

        >>> Sum(i, hs0)(ket_i) == Sum(i, hs=hs0)(ket_i) == s
        True

    Note that using :func:`Sum` is vastly more readable than the equivalent
    "manual" instantiation::

        >>> s == KetIndexedSum.create(ket_i, IndexOverFockSpace(i, hs=hs0))
        True

    By nesting calls to `Sum`, you can instantiate sums running over multiple
    indices::

        >>> unicode( Sum(i)(Sum(j)(ket_i * ket_j.dag())) )
        '∑_{i,j ∈ ℌ₀} |i⟩⟨j|⁽⁰⁾'

    Giving two integers in addition to the index `i` in `args`, the index will
    run between the two values::

        >>> unicode( Sum(i, 1, 10)(ket_i) )
        '∑_{i=1}^{10} |i⟩⁽⁰⁾'
        >>> Sum(i, 1, 10)(ket_i) == Sum(i, 1, to=10)(ket_i)
        True

    You may also include an optional step width, either as a third integer or
    using the `step` keyword argument.

        >>> #unicode( Sum(i, 1, 10, step=2)(ket_i) ) # TODO

    Lastly, by passing a tuple or list of values, the index will run over all
    the elements in that tuple or list::

        >>> unicode( Sum(i, (1, 2, 3))(ket_i))
        '∑_{i ∈ {1,2,3}} |i⟩⁽⁰⁾'
    """
    dispatch_table = {
        tuple(): _sum_over_fockspace,
        (LocalSpace, ): _sum_over_fockspace,
        (list, ): _sum_over_list,
        (tuple, ): _sum_over_list,
        (int, ): _sum_over_range,
        (int, int): _sum_over_range,
        (int, int, int): _sum_over_range,
    }
    key = tuple((type(arg) for arg in args))
    try:
        idx_range_func = dispatch_table[key]
    except KeyError:
        raise TypeError("No implementation for args of type %s" % str(key))

    def sum(term):
        idx_range = idx_range_func(term, idx, *args, **kwargs)
        return term._indexed_sum_cls.create(term, idx_range)

    return sum


def ensure_local_space(hs):
    """Ensure that the given `hs` is an instance of :class:`.LocalSpace`.

    If `hs` an instance of :class:`str` or :class:`int`, it will be converted
    to a :class:`.LocalSpace`. If it already is a :class:`.LocalSpace`, `hs`
    will be returned unchanged.

    Raises:
        TypeError: If `hs` is not a :class:`.LocalSpace`, :class:`str`, or
            :class:`int`.

    Returns:
        LocalSpace: original or converted `hs`

    Examples:
        >>> srepr(ensure_local_space(0))
        "LocalSpace('0')"
        >>> srepr(ensure_local_space('tls'))
        "LocalSpace('tls')"
        >>> srepr(ensure_local_space(LocalSpace(0)))
        "LocalSpace('0')"
        >>> srepr(ensure_local_space(LocalSpace(0) * LocalSpace(1)))
        Traceback (most recent call last):
           ...
        TypeError: hs must be a LocalSpace
    """
    if isinstance(hs, (str, int)):
        hs = LocalSpace(hs)
    if not isinstance(hs, LocalSpace):
        raise TypeError("hs must be a LocalSpace")
    return hs


def _series_expand_combine_prod(c1, c2, order):
    """Given the result of the ``c1._series_expand(...)`` and
    ``c2._series_expand(...)``, construct the result of
    ``(c1*c2)._series_expand(...)``
    """
    from qnet.algebra.core.scalar_algebra import Zero
    res = []
    c1 = list(c1)
    c2 = list(c2)
    for n in range(order + 1):
        summands = []
        for k in range(n + 1):
            if c1[k].is_zero or c2[n-k].is_zero:
                summands.append(Zero)
            else:
                summands.append(c1[k] * c2[n - k])
        sum = summands[0]
        for summand in summands[1:]:
            if summand != 0:
                sum += summand
        res.append(sum)
    return tuple(res)
