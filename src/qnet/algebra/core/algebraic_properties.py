import logging

from .abstract_algebra import (
    ScalarTimesExpression, all_symbols, LOG, LEVEL, LOG_NO_MATCH, )
from .exceptions import (
    CannotSimplify, UnequalSpaces,
    SpaceTooLargeError, )
from .scalar_types import SCALAR_TYPES
from ..pattern_matching import ProtoExpr, match_pattern

__all__ = []
__private__ = [
    'assoc', 'assoc_indexed', 'idem', 'orderby', 'filter_neutral',
    'match_replace', 'match_replace_binary', 'check_cdims',
    'convert_to_spaces', 'empty_trivial', 'implied_local_space',
    'delegate_to_method', 'scalars_to_op', 'disjunct_hs_zero',
    'commutator_order', 'check_kets_same_space', 'check_op_ket_space',
    'accept_bras', 'basis_ket_zero_outside_hs']


def assoc(cls, ops, kwargs):
    """Associatively expand out nested arguments of the flat class.
    E.g.::

        >>> from qnet import Operation
        >>> class Plus(Operation):
        ...     _simplifications = [assoc, ]
        >>> Plus.create(1,Plus(2,3))
        Plus(1, 2, 3)
    """
    expanded = [(o,) if not isinstance(o, cls) else o.operands for o in ops]
    return sum(expanded, ()), kwargs


def assoc_indexed(cls, ops, kwargs):
    r"""Flatten nested indexed structures while pulling out possible prefactors

    For example, for an :class:`.IndexedSum`:

    .. math::

        \sum_j \left( a \sum_i \dots \right) = a \sum_{j, i} \dots
    """
    term, *ranges = ops

    if isinstance(term, cls):
        coeff = 1
    elif isinstance(term, ScalarTimesExpression):
        coeff = term.coeff
        term = term.term
        if not isinstance(term, cls):
            return ops, kwargs
    else:
        return ops, kwargs

    term = term.make_disjunct_indices(*ranges)
    combined_ranges = tuple(ranges) + term.ranges

    if coeff == 1:
        return cls(term.term, *combined_ranges)
    else:
        bound_symbols = set([r.index_symbol for r in combined_ranges])
        if len(all_symbols(coeff).intersection(bound_symbols)) == 0:
            return coeff * cls(term.term, *combined_ranges)
        else:
            return cls(coeff * term.term, *combined_ranges)


def idem(cls, ops, kwargs):
    """Remove duplicate arguments and order them via the cls's order_key key
    object/function.
    E.g.::

        >>> from qnet import Operation
        >>> class Set(Operation):
        ...     order_key = lambda val: val
        ...     _simplifications = [idem, ]
        >>> Set.create(1,2,3,1,3)
        Set(1, 2, 3)
    """
    return sorted(set(ops), key=cls.order_key), kwargs


def orderby(cls, ops, kwargs):
    """Re-order arguments via the class's ``order_key`` key object/function.
    Use this for commutative operations:
    E.g.::

        >>> from qnet import Operation
        >>> class Times(Operation):
        ...     order_key = lambda val: val
        ...     _simplifications = [orderby, ]
        >>> Times.create(2,1)
        Times(1, 2)
    """
    return sorted(ops, key=cls.order_key), kwargs


def filter_neutral(cls, ops, kwargs):
    """Remove occurrences of a neutral element from the argument/operand list,
    if that list has at least two elements.  To use this, one must also specify
    a neutral element, which can be anything that allows for an equality check
    with each argument.  E.g.::

        >>> from qnet import Operation
        >>> class X(Operation):
        ...     neutral_element = 1
        ...     _simplifications = [filter_neutral, ]
        >>> X.create(2,1,3,1)
        X(2, 3)
    """
    c_n = cls.neutral_element
    if len(ops) == 0:
        return c_n
    fops = [op for op in ops if c_n != op]  # op != c_n does NOT work
    if len(fops) > 1:
        return fops, kwargs
    elif len(fops) == 1:
        # the remaining operand is the single non-trivial one
        return fops[0]
    else:
        # the original list of operands consists only of neutral elements
        return ops[0]


def match_replace(cls, ops, kwargs):
    """Match and replace a full operand specification to a function that
    provides a replacement for the whole expression
    or raises a :exc:`.CannotSimplify` exception.
    E.g.

    First define an operation::

        >>> from collections import OrderedDict
        >>> from qnet import Operation, wc, pattern, pattern_head
        >>> class Invert(Operation):
        ...     _rules = OrderedDict()
        ...     _simplifications = [match_replace, ]

    Then some _rules::

        >>> from qnet import wc
        >>> A = wc("A")
        >>> A_float = wc("A", head=float)
        >>> Invert_A = pattern(Invert, A)
        >>> Invert._rules.update([
        ...     ('r1', (pattern_head(Invert_A), lambda A: A)),
        ...     ('r2', (pattern_head(A_float), lambda A: 1./A)),
        ... ])

    Check rule application::

        >>> from qnet.printing import srepr
        >>> print(srepr(Invert.create("hallo")))  # matches no rule
        Invert('hallo')
        >>> Invert.create(Invert("hallo"))        # matches first rule
        'hallo'
        >>> Invert.create(.2)                     # matches second rule
        5.0

    A pattern can also have the same wildcard appear twice::

        >>> class X(Operation):
        ...     _rules = {
        ...         'r1': (pattern_head(A, A), lambda A: A),
        ...     }
        ...     _simplifications = [match_replace, ]
        >>> X.create(1,2)
        X(1, 2)
        >>> X.create(1,1)
        1

    """
    expr = ProtoExpr(ops, kwargs)
    if LOG:
        logger = logging.getLogger(__name__ + '.create')
    for key, rule in cls._rules.items():
        pat, replacement = rule
        match_dict = match_pattern(pat, expr)
        if match_dict:
            try:
                replaced = replacement(**match_dict)
                if LOG:
                    logger.debug(
                        "%sRule %s.%s: (%s, %s) -> %s", ("  " * (LEVEL)),
                        cls.__name__, key, expr.args, expr.kwargs, replaced)
                return replaced
            except CannotSimplify:
                if LOG_NO_MATCH:
                    logger.debug(
                        "%sRule %s.%s: no match: CannotSimplify",
                        ("  " * (LEVEL)), cls.__name__, key)
                continue
        else:
            if LOG_NO_MATCH:
                logger.debug(
                    "%sRule %s.%s: no match: %s", ("  " * (LEVEL)),
                    cls.__name__, key, match_dict.reason)
    # No matching rules
    return ops, kwargs


def _get_binary_replacement(first, second, cls):
    """Helper function for match_replace_binary"""
    expr = ProtoExpr([first, second], {})
    if LOG:
        logger = logging.getLogger(__name__ + '.create')
    for key, rule in cls._binary_rules.items():
        pat, replacement = rule
        match_dict = match_pattern(pat, expr)
        if match_dict:
            try:
                replaced = replacement(**match_dict)
                if LOG:
                    logger.debug(
                        "%sRule %s.%s: (%s, %s) -> %s", ("  " * (LEVEL)),
                        cls.__name__, key, expr.args, expr.kwargs, replaced)
                return replaced
            except CannotSimplify:
                continue
    return None


def match_replace_binary(cls, ops, kwargs):
    """Similar to func:`match_replace`, but for arbitrary length operations,
    such that each two pairs of subsequent operands are matched pairwise.

        >>> from qnet import wc, Operation, pattern_head
        >>> A = wc("A")
        >>> class FilterDupes(Operation):
        ...     _binary_rules = {
        ...          'filter_dupes': (pattern_head(A,A), lambda A: A)}
        ...     _simplifications = [match_replace_binary, assoc]
        ...     neutral_element = 0
        >>> FilterDupes.create(1,2,3,4)         # No duplicates
        FilterDupes(1, 2, 3, 4)
        >>> FilterDupes.create(1,2,2,3,4)       # Some duplicates
        FilterDupes(1, 2, 3, 4)

    Note that this only works for *subsequent* duplicate entries:

        >>> FilterDupes.create(1,2,3,2,4)       # No *subsequent* duplicates
        FilterDupes(1, 2, 3, 2, 4)

    Any operation that uses binary reduction must be associative and define a
    neutral element. The binary rules must be compatible with associativity,
    i.e. there is no specific order in which the rules are applied to pairs of
    operands.
    """
    assert assoc in cls._simplifications, (
        cls.__name__ + " must be associative to use match_replace_binary")
    assert hasattr(cls, 'neutral_element'), (
        cls.__name__ + " must define a neutral element to use "
                       "match_replace_binary")
    fops = _match_replace_binary(cls, list(ops))
    if len(fops) == 1:
        return fops[0]
    elif len(fops) == 0:
        return cls.neutral_element
    else:
        return fops, kwargs


def _match_replace_binary(cls, ops: list) -> list:
    """Reduce list of `ops`"""
    n = len(ops)
    if n <= 1:
        return ops
    ops_left = ops[:n // 2]
    ops_right = ops[n // 2:]
    return _match_replace_binary_combine(
        cls,
        _match_replace_binary(cls, ops_left),
        _match_replace_binary(cls, ops_right))


def _match_replace_binary_combine(cls, a: list, b: list) -> list:
    """combine two fully reduced lists a, b"""
    if len(a) == 0 or len(b) == 0:
        return a + b
    r = _get_binary_replacement(a[-1], b[0], cls)
    if r is None:
        return a + b
    if r == cls.neutral_element:
        return _match_replace_binary_combine(cls, a[:-1], b[1:])
    if isinstance(r, cls):
        r = list(r.args)
    else:
        r = [r, ]
    return _match_replace_binary_combine(
        cls,
        _match_replace_binary_combine(cls, a[:-1], r),
        b[1:])


def check_cdims(cls, ops, kwargs):
    """Check that all operands (`ops`) have equal channel dimension."""
    if not len({o.cdim for o in ops}) == 1:
        raise ValueError("Not all operands have the same cdim:" + str(ops))
    return ops, kwargs


def convert_to_spaces(cls, ops, kwargs):
    """For all operands that are merely of type str or int, substitute
    LocalSpace objects with corresponding labels:
    For a string, just itself, for an int, a string version of that int.
    """
    from qnet.algebra.core.hilbert_space_algebra import (
        HilbertSpace, LocalSpace)
    cops = [o if isinstance(o, HilbertSpace) else LocalSpace(o) for o in ops]
    return cops, kwargs


def empty_trivial(cls, ops, kwargs):
    """A ProductSpace of zero Hilbert spaces should yield the TrivialSpace"""
    from qnet.algebra.core.hilbert_space_algebra import TrivialSpace
    if len(ops) == 0:
        return TrivialSpace
    else:
        return ops, kwargs


def implied_local_space(*, arg_index=None, keys=None):
    """Return a simplification that converts the positional argument
    `arg_index` from (str, int) to :class:`.LocalSpace`, as well as any keyword
    argument with one of the given keys"""
    from qnet.algebra.core.hilbert_space_algebra import (
        HilbertSpace, LocalSpace)

    def args_to_local_space(cls, args, kwargs):
        """Convert (str, int) of selected args to :class:`.LocalSpace`"""
        if isinstance(args[arg_index], LocalSpace):
            new_args = args
        else:
            if isinstance(args[arg_index], (int, str)):
                hs = LocalSpace(args[arg_index])
            else:
                hs = args[arg_index]
                assert isinstance(hs, HilbertSpace)
            new_args = (tuple(args[:arg_index]) + (hs,) +
                        tuple(args[arg_index + 1:]))
        return new_args, kwargs

    def kwargs_to_local_space(cls, args, kwargs):
        """Convert (str, int) of selected kwargs to LocalSpace"""
        if all([isinstance(kwargs[key], LocalSpace) for key in keys]):
            new_kwargs = kwargs
        else:
            new_kwargs = {}
            for key, val in kwargs.items():
                if key in keys:
                    if isinstance(val, (int, str)):
                        val = LocalSpace(val)
                    assert isinstance(val, HilbertSpace)
                new_kwargs[key] = val
        return args, new_kwargs

    def to_local_space(cls, args, kwargs):
        """Convert (str, int) of selected args and kwargs to LocalSpace"""
        new_args, __ = args_to_local_space(args, kwargs, arg_index)
        __, new_kwargs = kwargs_to_local_space(args, kwargs, keys)
        return new_args, new_kwargs

    if (arg_index is not None) and (keys is None):
        return args_to_local_space
    elif (arg_index is None) and (keys is not None):
        return kwargs_to_local_space
    elif (arg_index is not None) and (keys is not None):
        return to_local_space
    else:
        raise ValueError("must give at least one of arg_index and keys")


def delegate_to_method(mtd):
    """Create a simplification rule that delegates the instantiation to the
    method `mtd` of the operand (if defined)"""

    def _delegate_to_method(cls, ops, kwargs):
        assert len(ops) == 1
        op, = ops
        if hasattr(op, mtd):
            return getattr(op, mtd)()
        else:
            return ops, kwargs

    return _delegate_to_method


def scalars_to_op(cls, ops, kwargs):
    r'''Convert any scalar $\alpha$ in `ops` into an operator $\alpha
    \identity$'''
    from qnet.algebra.core.operator_algebra import (
        ScalarTimesOperator, IdentityOperator)
    op_ops = []
    for op in ops:
        if isinstance(op, SCALAR_TYPES):
            op_ops.append(ScalarTimesOperator.create(op, IdentityOperator))
        else:
            op_ops.append(op)
    return op_ops, kwargs


def disjunct_hs_zero(cls, ops, kwargs):
    """Return ZeroOperator if all the operators in `ops` have a disjunct
    Hilbert space, or an unchanged `ops`, `kwargs` otherwise
    """
    from qnet.algebra.core.hilbert_space_algebra import TrivialSpace
    from qnet.algebra.core.operator_algebra import ZeroOperator
    hilbert_spaces = []
    for op in ops:
        try:
            hs = op.space
        except AttributeError:  # scalars
            hs = TrivialSpace
        for hs_prev in hilbert_spaces:
            if not hs.isdisjoint(hs_prev):
                return ops, kwargs
        hilbert_spaces.append(hs)
    return ZeroOperator


def commutator_order(cls, ops, kwargs):
    """Apply anti-commutative property of the commutator to apply a standard
    ordering of the commutator arguments
    """
    from qnet.algebra.core.operator_algebra import Commutator
    assert len(ops) == 2
    if cls.order_key(ops[1]) < cls.order_key(ops[0]):
        return -1 * Commutator.create(ops[1], ops[0])
    else:
        return ops, kwargs


def check_kets_same_space(cls, ops, kwargs):
    """Check that all operands are from the same Hilbert space."""
    from qnet.algebra.core.state_algebra import Ket, ZeroKet
    if not all([isinstance(o, Ket) for o in ops]):
        raise TypeError("All operands must be Kets")
    if not len({o.space for o in ops if o is not ZeroKet}) == 1:
        raise UnequalSpaces(str(ops))
    return ops, kwargs


def check_op_ket_space(cls, ops, kwargs):
    """Check that all operands are from the same Hilbert space."""
    op, ket = ops
    if not op.space <= ket.space:
        raise SpaceTooLargeError(str(op.space) + " <!= " + str(ket.space))
    return ops, kwargs


def accept_bras(cls, ops, kwargs):
    """Accept operands that are all bras, and turn that into to bra of the
    operation applied to all corresponding kets"""
    from qnet.algebra.core.state_algebra import Bra
    kets = []
    for bra in ops:
        if isinstance(bra, Bra):
            kets.append(bra.ket)
        else:
            return ops, kwargs
    return Bra.create(cls.create(*kets, **kwargs))


def basis_ket_zero_outside_hs(cls, ops, kwargs):
    """For ``BasisKet.create(ind, hs)`` with an integer label `ind`, return a
    :class:`ZeroKet` if `ind` is outside of the range of the underlying Hilbert
    space
    """
    from qnet.algebra.core.state_algebra import ZeroKet
    ind, = ops
    hs = kwargs['hs']
    if isinstance(ind, int):
        if ind < 0 or (hs._dimension is not None and ind >= hs._dimension):
            return ZeroKet
    return ops, kwargs