r"""
This module features classes and functions to define and manipulate symbolic
Operator expressions.  For more details see :ref:`operator_algebra`.

For a list of all properties and methods of an operator object, see the
documentation for the basic :class:`Operator` class.
"""
import re
from abc import ABCMeta
from collections import OrderedDict, defaultdict
from itertools import product as cartesian_product

from sympy import Expr as SympyExpr, I, sqrt, sympify

from .abstract_quantum_algebra import (
    ScalarTimesQuantumExpression, QuantumExpression, QuantumSymbol,
    QuantumOperation, QuantumPlus, QuantumTimes, SingleQuantumOperation,
    QuantumAdjoint, QuantumIndexedSum, ensure_local_space)
from .algebraic_properties import (
    assoc, assoc_indexed, commutator_order, delegate_to_method,
    disjunct_hs_zero, filter_neutral, implied_local_space, match_replace,
    match_replace_binary, orderby, scalars_to_op, indexed_sum_over_const,
    indexed_sum_over_kronecker)
from .exceptions import CannotSimplify, BasisNotSetError
from .hilbert_space_algebra import (
    HilbertSpace, LocalSpace, ProductSpace, TrivialSpace, )
from .scalar_algebra import Scalar, ScalarValue, is_scalar
from .scalar_algebra import is_scalar
from ..pattern_matching import pattern, pattern_head, wc
from ...utils.indices import SymbolicLabelBase
from ...utils.ordering import FullCommutativeHSOrder
from ...utils.singleton import Singleton, singleton_object

sympyOne = sympify(1)

# for hilbert space dimensions less than or equal to this,
# compute numerically PseudoInverse and NullSpaceProjector representations
DENSE_DIMENSION_LIMIT = 1000

__all__ = [
    'Adjoint', 'Create', 'Destroy', 'Displace', 'Jminus', 'Jplus',
    'Jz', 'LocalOperator', 'LocalSigma', 'NullSpaceProjector', 'Operator',
    'OperatorPlus', 'OperatorPlusMinusCC', 'OperatorSymbol', 'OperatorTimes',
    'OperatorTrace', 'Phase', 'PseudoInverse', 'ScalarTimesOperator',
    'Squeeze', 'Jmjmcoeff', 'Jpjmcoeff', 'Jzjmcoeff', 'LocalProjector', 'X',
    'Y', 'Z', 'adjoint', 'create_operator_pm_cc', 'decompose_space',
    'expand_operator_pm_cc', 'factor_coeff', 'factor_for_trace', 'get_coeffs',
    'II', 'IdentityOperator', 'ZeroOperator', 'Commutator',
    'OperatorIndexedSum', 'tr']

__private__ = []  # anything not in __all__ must be in __private__


###############################################################################
# Abstract base classes
###############################################################################


class Operator(QuantumExpression, metaclass=ABCMeta):
    """Base class for all quantum operators."""

    def pseudo_inverse(self):
        """The pseudo-Inverse of the Operator, i.e., it inverts the operator on
        the orthogonal complement of its nullspace"""
        return PseudoInverse.create(self)

    def expand_in_basis(self, basis_states=None, hermitian=False):
        """Write the operator as an expansion into all
        :class:`KetBras <.KetBra>`
        spanned by `basis_states`.

        Args:
            basis_states (list or None): List of basis states (:class:`.State`
                instances) into which to expand the operator. If None, use the
                operator's `space.basis_states`
            hermitian (bool): If True, assume that the operator is Hermitian
                and represent all elements in the lower triangle of the
                expansion via :class:`OperatorPlusMinusCC`. This is meant to
                enhance readability

        Raises:
            .BasisNotSetError: If `basis_states` is None and the operator's
                Hilbert space has no well-defined basis

        Example:

            >>> hs = LocalSpace(1, basis=('g', 'e'))
            >>> op = LocalSigma('g', 'e', hs=hs) + LocalSigma('e', 'g', hs=hs)
            >>> print(ascii(op, sig_as_ketbra=False))
            sigma_e,g^(1) + sigma_g,e^(1)
            >>> print(ascii(op.expand_in_basis()))
            |e><g|^(1) + |g><e|^(1)
            >>> print(ascii(op.expand_in_basis(hermitian=True)))
            |g><e|^(1) + c.c.
        """
        from qnet.algebra.core.state_algebra import KetBra
        # KetBra is imported locally to avoid circular imports
        if basis_states is None:
            basis_states = list(self.space.basis_states)
        else:
            basis_states = list(basis_states)
        diag_terms = []
        terms = []
        for i, ket_i in enumerate(basis_states):
            for j, ket_j in enumerate(basis_states):
                if i > j and hermitian:
                    continue
                op_ij = (ket_i.dag() * self * ket_j).expand()
                ketbra = KetBra(ket_i, ket_j)
                term = op_ij * ketbra
                if term is not ZeroOperator:
                    if i == j:
                        diag_terms.append(op_ij * ketbra)
                    else:
                        terms.append(op_ij * ketbra)
        if hermitian:
            res = OperatorPlus.create(*diag_terms)
            if len(terms) > 0:
                res = res + OperatorPlusMinusCC(OperatorPlus.create(*terms))
            return res
        else:
            return (
                OperatorPlus.create(*diag_terms) +
                OperatorPlus.create(*terms))


class LocalOperator(Operator, metaclass=ABCMeta):
    """Base class for all kinds of operators that act *locally*,
    i.e. only on a single degree of freedom.

    All :class:`LocalOperator` instances have a fixed associated identifier
    (symbol) that is used when printing that operator. A custom identifier can
    be used through the associated :class:`.LocalSpace`'s
    `local_identifiers` parameter. For example::

        >>> hs1_custom = LocalSpace(1, local_identifiers={'Destroy': 'b'})
        >>> b = Destroy(hs=hs1_custom)
        >>> ascii(b)
        'b^(1)'
    """

    _simplifications = [implied_local_space(keys=['hs', ]), ]

    _identifier = None  # must be overridden by subclasses!
    _dagger = False  # do representations include a dagger?
    _nargs = 0  # number of arguments
    _scalar_args = True  # convert args to Scalar?
    _rx_identifier = re.compile('^[A-Za-z][A-Za-z0-9]*(_[A-Za-z0-9().+-]+)?$')

    def __init__(self, *args, hs):
        if self._scalar_args:
            args = [ScalarValue.create(arg) for arg in args]
        hs = ensure_local_space(hs)
        self._hs = hs
        if self._identifier is None:
            raise TypeError(
                r"Can't instantiate abstract class %s with undefined "
                r"_identifier" % self.__class__.__name__)
        if len(args) != self._nargs:
            raise ValueError("expected %d arguments, gotten %d"
                             % (self._nargs, len(args)))
        super().__init__(*args, hs=hs)

    @property
    def space(self):
        """Hilbert space of the operator (:class:`.LocalSpace` instance)"""
        return self._hs

    @property
    def args(self):
        """The positional arguments used for instantiating the operator"""
        return tuple()

    @property
    def kwargs(self):
        """The keyword arguments used for instantiating the operator"""
        return OrderedDict([('hs', self._hs)])

    @property
    def identifier(self):
        """The identifier (symbol) that is used when printing the operator.

        A custom identifier can be used through the associated
        :class:`.LocalSpace`'s `local_identifiers` parameter. For example::

            >>> a = Destroy(hs=1)
            >>> a.identifier
            'a'
            >>> hs1_custom = LocalSpace(1, local_identifiers={'Destroy': 'b'})
            >>> b = Destroy(hs=hs1_custom)
            >>> b.identifier
            'b'
            >>> ascii(b)
            'b^(1)'
        """

        identifier = self._hs._local_identifiers.get(
            self.__class__.__name__, self._identifier)
        if not self._rx_identifier.match(identifier):
            raise ValueError(
                "identifier '%s' does not match pattern '%s'"
                % (identifier, self._rx_identifier.pattern))
        return identifier

    def _simplify_scalar(self, func):
        if self._scalar_args:
            args = [arg.simplify_scalar(func=func) for arg in self.args]
            return self.create(*args, hs=self.space)
        else:
            return super()._simplify_scalar(func=func)


###############################################################################
# Operator algebra elements
###############################################################################


class OperatorSymbol(QuantumSymbol, Operator):
    """Symbolic operator"""
    pass


@singleton_object
class IdentityOperator(Operator, metaclass=Singleton):
    """``IdentityOperator`` constant (singleton) object."""

    _order_index = 2

    @property
    def space(self):
        """:class:`.TrivialSpace`"""
        return TrivialSpace

    @property
    def args(self):
        return tuple()

    def _adjoint(self):
        return self

    def _pseudo_inverse(self):
        return self


II = IdentityOperator


@singleton_object
class ZeroOperator(Operator, metaclass=Singleton):
    """``ZeroOperator`` constant (singleton) object."""

    _order_index = 2

    @property
    def space(self):
        """:class:`.TrivialSpace`"""
        return TrivialSpace

    @property
    def args(self):
        return tuple()

    def _adjoint(self):
        return self

    def _pseudo_inverse(self):
        return self


class Destroy(LocalOperator):
    """Bosonic annihilation operator acting on a particular
    :class:`.LocalSpace` `hs`.

    It obeys the bosonic commutation relation::

        >>> Destroy(hs=1) * Create(hs=1) - Create(hs=1) * Destroy(hs=1)
        IdentityOperator
        >>> Destroy(hs=1) * Create(hs=2) - Create(hs=2) * Destroy(hs=1)
        ZeroOperator
    """

    _identifier = 'a'
    _dagger = False
    _rx_identifier = re.compile('^[A-Za-z][A-Za-z0-9]*$')

    def __init__(self, *, hs):
        super().__init__(hs=hs)

    def _adjoint(self):
        return Create(hs=self.space)

    @property
    def identifier(self):
        """The identifier (symbols) that is used when printing the annihilation
        operator. This is identical to the identifier of :class:`Create`. A
        custom identifier for both :class:`Destroy` and :class:`Create` can be
        set through the `local_identifiers` parameter of the associated Hilbert
        space::

            >>> hs_custom = LocalSpace(0, local_identifiers={'Destroy': 'b'})
            >>> Create(hs=hs_custom).identifier
            'b'
            >>> Destroy(hs=hs_custom).identifier
            'b'
        """
        identifier = self._hs._local_identifiers.get(
            self.__class__.__name__, self._hs._local_identifiers.get(
                'Create', self._identifier))
        if not self._rx_identifier.match(identifier):
            raise ValueError(
                "identifier '%s' does not match pattern '%s'"
                % (identifier, self._rx_identifier.pattern))
        return identifier


class Create(LocalOperator):
    """Bosonic creation operator acting on a particular :class:`.LocalSpace`
    `hs`. It is the adjoint of :class:`Destroy`.
    """

    _identifier = 'a'
    _dagger = True
    _rx_identifier = re.compile('^[A-Za-z][A-Za-z0-9]*$')

    def __init__(self, *, hs):
        super().__init__(hs=hs)

    def _adjoint(self):
        return Destroy(hs=self.space)

    @property
    def identifier(self):
        """The identifier (symbols) that is used when printing the creation
        operator. This is identical to the identifier of :class:`Destroy`"""
        identifier = self._hs._local_identifiers.get(
            self.__class__.__name__, self._hs._local_identifiers.get(
                'Destroy', self._identifier))
        if not self._rx_identifier.match(identifier):
            raise ValueError(
                "identifier '%s' does not match pattern '%s'"
                % (identifier, self._rx_identifier.pattern))
        return identifier


class Jz(LocalOperator):
    """$\Op{J}_z$ is the $z$ component of a general spin operator acting
    on a particular :class:`.LocalSpace` `hs` of freedom with well defined spin
    quantum number $s$.  It is Hermitian::

        >>> print(ascii(Jz(hs=1).adjoint()))
        J_z^(1)

    :class:`Jz`, :class:`Jplus` and :class:`Jminus` satisfy the angular
    momentum commutator algebra::

        >>> print(ascii((Jz(hs=1) * Jplus(hs=1) -
        ...              Jplus(hs=1)*Jz(hs=1)).expand()))
        J_+^(1)

        >>> print(ascii((Jz(hs=1) * Jminus(hs=1) -
        ...              Jminus(hs=1)*Jz(hs=1)).expand()))
        -J_-^(1)

        >>> print(ascii((Jplus(hs=1) * Jminus(hs=1)
        ...              - Jminus(hs=1)*Jplus(hs=1)).expand()))
        2 * J_z^(1)
        >>> Jplus(hs=1).dag() == Jminus(hs=1)
        True
        >>> Jminus(hs=1).dag() == Jplus(hs=1)
        True

    Printers should represent this operator with the default identifier::

        >>> Jz._identifier
        'J_z'

    A custom identifier may be define using `hs`'s `local_identifiers`
    argument.
    """

    _identifier = 'J_z'

    def __init__(self, *, hs):
        super().__init__(hs=hs)

    def _adjoint(self):
        return self


class Jplus(LocalOperator):
    """ $\Op{J}_{+} = \Op{J}_x + i \op{J}_y$ is the raising ladder operator
    of a general spin operator acting on a particular :class:`.LocalSpace` `hs`
    with well defined spin quantum number $s$.  It's adjoint is the
    lowering operator::

        >>> print(ascii(Jplus(hs=1).adjoint()))
        J_-^(1)

    :class:`Jz`, :class:`Jplus` and :class:`Jminus` satisfy that angular
    momentum commutator algebra, see :class:`Jz`

    Printers should represent this operator with the default identifier::

        >>> Jplus._identifier
        'J_+'

    A custom identifier may be define using `hs`'s `local_identifiers`
    argument.
    """

    _identifier = 'J_+'

    def __init__(self, *, hs):
        super().__init__(hs=hs)

    def _adjoint(self):
        return Jminus(hs=self.space)


class Jminus(LocalOperator):
    """$\Op{J}_{-} = \Op{J}_x - i \op{J}_y$ is lowering ladder operator of a
    general spin operator acting on a particular :class:`.LocalSpace` `hs`
    with well defined spin quantum number $s$.  It's adjoint is the raising
    operator::

        >>> print(ascii(Jminus(hs=1).adjoint()))
        J_+^(1)

    :class:`Jz`, :class:`Jplus` and :class:`Jminus` satisfy that angular
    momentum commutator algebra, see :class:`Jz`.

    Printers should represent this operator with the default identifier::

        >>> Jminus._identifier
        'J_-'

    A custom identifier may be define using `hs`'s `local_identifiers`
    argument.
    """

    _identifier = 'J_-'

    def __init__(self, *, hs):
        super().__init__(hs=hs)

    def _adjoint(self):
        return Jplus(hs=self.space)


class Phase(LocalOperator):
    r"""Unitary "phase" operator

    .. math::

        \op{P}_{\rm hs}(\phi) =
        \exp\left(i \phi \Op{a}_{\rm hs}^\dagger \Op{a}_{\rm hs}\right)

    where :math:`a_{\rm hs}` is the annihilation operator acting on the
    :class:`.LocalSpace` `hs`.

    Printers should represent this operator with the default identifier::

        >>> Phase._identifier
        'Phase'

    A custom identifier may be define using `hs`'s `local_identifiers`
    argument.
    """
    _identifier = 'Phase'
    _nargs = 1
    _rules = OrderedDict()
    _simplifications = [implied_local_space(keys=['hs', ]), match_replace]

    def __init__(self, phi, *, hs):
        self.phi = phi  #: Phase $\phi$
        super().__init__(phi, hs=hs)

    @property
    def args(self):
        r'''List of arguments of the operator, containing the phase $\phi$ as
        the only element'''
        return (self.phi,)

    def _adjoint(self):
        return Phase.create(-self.phi.conjugate(), hs=self.space)

    def _pseudo_inverse(self):
        return Phase.create(-self.phi, hs=self.space)


class Displace(LocalOperator):
    r"""Unitary coherent displacement operator

    .. math::

        \op{D}_{\rm hs}(\alpha) =
        \exp\left({\alpha \Op{a}_{\rm hs}^\dagger -
                   \alpha^* \Op{a}_{\rm hs}}\right)

    where :math:`\Op{a}_{\rm hs}` is the annihilation operator acting on the
    :class:`.LocalSpace` `hs`.

    Printers should represent this operator with the default identifier::

        >>> Displace._identifier
        'D'

    A custom identifier may be define using `hs`'s `local_identifiers`
    argument.
    """
    _identifier = 'D'
    _nargs = 1
    _rules = OrderedDict()
    _simplifications = [implied_local_space(keys=['hs', ]), match_replace]

    def __init__(self, alpha, *, hs):
        self.alpha = alpha  #: Displacement amplitude $\alpha$
        super().__init__(alpha, hs=hs)

    @property
    def args(self):
        r'''List of arguments of the operator, containing the displacement
        amplitude $\alpha$ as the only element'''
        return (self.alpha,)

    def _adjoint(self):
        return Displace.create(-self.alpha, hs=self.space)

    _pseudo_inverse = _adjoint


class Squeeze(LocalOperator):
    r"""Unitary Squeezing operator

    .. math::

        \Op{S}_{\rm hs}(\eta) =
        \exp {\left( \frac{\eta}{2} {\Op{a}_{\rm hs}^\dagger}^2 -
                     \frac{\eta^*}{2} {\Op{a}_{\rm hs}}^2 \right)}

    where :math:`\Op{a}_{\rm hs}` is the annihilation operator acting on the
    :class:`.LocalSpace` `hs`.

    Printers should represent this operator with the default identifier::

        >>> Squeeze._identifier
        'Squeeze'

    A custom identifier may be define using `hs`'s `local_identifiers`
    argument.
    """
    _identifier = "Squeeze"
    _nargs = 1
    _rules = OrderedDict()
    _simplifications = [implied_local_space(keys=['hs', ]), match_replace]

    def __init__(self, eta, *, hs):
        self.eta = eta  #: sqeezing parameter $\eta$
        super().__init__(eta, hs=hs)

    @property
    def args(self):
        return (self.eta,)

    def _adjoint(self):
        return Squeeze(-self.eta, hs=self.space)

    _pseudo_inverse = _adjoint


class LocalSigma(LocalOperator):
    r'''A local level flip operator operator acting on a particular
    :class:`.LocalSpace` `hs`.

    .. math::

        \Op{\sigma}_{jk}^{\rm hs} =
        \left| j\right\rangle_{\rm hs} \left \langle k \right |_{\rm hs}

    For $j=k$ this becomes a projector $\Op{P}_k$ onto the eigenstate
    $\ket{k}$; see :class:`LocalProjector`.

    Args:
        j (int or str): The label or index identifying $\ket{j}$
        k (int or str):  The label or index identifying $\ket{k}$
        hs (HilbertSpace or int or str): The Hilbert space on which the
            operator acts

    Note:
        The parameters `j` or `k` may be an integer or a string. A string
        refers to the label of an eigenstate in the basis of `hs`, which needs
        to be set. An integer refers to the (zero-based) index of eigenstate of
        the Hilbert space. This works if `hs` has an unknown dimension.

    Raises:
        ValueError: If `j` or `k` are invalid value for the given `hs`

    Printers should represent this operator either in braket notation, or using
    the operator identifier

        >>> LocalSigma(0, 0, hs=0).identifier
        'sigma'
    '''

    _identifier = "sigma"
    _rx_identifier = re.compile('^[A-Za-z][A-Za-z0-9]*$')
    _nargs = 2
    _scalar_args = False  # args are labels, not scalar coefficients
    _rules = OrderedDict()
    _simplifications = [implied_local_space(keys=['hs', ]), match_replace]

    def __init__(self, j, k, *, hs):
        if isinstance(hs, (str, int)):
            hs = LocalSpace(hs)
        for ind_jk in range(2):
            jk = j if ind_jk == 0 else k
            hs._check_basis_label_type(jk)
            if isinstance(jk, str):
                if not hs.has_basis:
                    raise ValueError(
                        "Invalid to give label %s for Hilbert space %s that "
                        "has no basis" % (jk, hs))
            elif isinstance(jk, int):
                if jk < 0:
                    raise ValueError("Index j/k=%s must be >= 0" % jk)
                if hs.has_basis:
                    if jk >= hs.dimension:
                        raise ValueError(
                            "Index j/k=%s must be < the Hilbert space "
                            "dimension %d" % (jk, hs.dimension))
                    if ind_jk == 0:
                        j = hs.basis_labels[jk]
                    else:
                        k = hs.basis_labels[jk]
            elif isinstance(jk, SymbolicLabelBase):
                pass  # use j, k as-is
            else:
                # Interal error: mismatch with hs._basis_label_types
                raise NotImplementedError()
        self.j = j  #: label/index of eigenstate  $\ket{j}$
        self.k = k  #: label/index of eigenstate  $\ket{k}$
        super().__init__(j, k, hs=hs)

    @property
    def args(self):
        """The two eigenstate labels `j` and `k` that the operator connects"""
        return self.j, self.k

    @property
    def index_j(self):
        """Index `j` or (zero-based) index of the label `j` in the basis"""
        if isinstance(self.j, (int, SymbolicLabelBase)):
            return self.j
        else:
            return self.space.basis_labels.index(self.j)

    @property
    def index_k(self):
        """Index `k` or (zero-based) index of the label `k` in the basis"""
        if isinstance(self.k, (int, SymbolicLabelBase)):
            return self.k
        else:
            return self.space.basis_labels.index(self.k)

    def raise_jk(self, j_incr=0, k_incr=0):
        r'''Return a new :class:`LocalSigma` instance with incremented `j`,
        `k`, on the same Hilbert space:

        .. math::

            \Op{\sigma}_{jk}^{\rm hs} \rightarrow \Op{\sigma}_{j'k'}^{\rm hs}

        This is the result of multiplying $\Op{\sigma}_{jk}^{\rm hs}$
        with any raising or lowering operators.

        If $j'$ or $k'$ are outside the Hilbert space ${\rm hs}$, the result is
        the :obj:`ZeroOperator` .

        Args:
            j_incr (int): The increment between labels $j$ and $j'$
            k_incr (int): The increment between labels $k$ and $k'$. Both
                increments may be negative.
        '''
        try:
            if isinstance(self.j, int):
                new_j = self.j + j_incr
            else:  # str
                new_j = self.space.next_basis_label_or_index(self.j, j_incr)
            if isinstance(self.k, int):
                new_k = self.k + k_incr
            else:  # str or SymbolicLabelBase
                new_k = self.space.next_basis_label_or_index(self.k, k_incr)
            return LocalSigma.create(new_j, new_k, hs=self.space)
        except (IndexError, ValueError):
            return ZeroOperator

    def _adjoint(self):
        return LocalSigma(j=self.k, k=self.j, hs=self.space)


class LocalProjector(LocalSigma):
    """A projector onto a specific level.

    Args:
        j (int or str): The label or index identifying the state onto which
            is projected
        hs (HilbertSpace): The Hilbert space on which the operator acts
    """
    _identifier = "Pi"
    _nargs = 2  # must be 2 because that's how we call super().__init__

    def __init__(self, j, *, hs):
        super().__init__(j=j, k=j, hs=hs)

    @property
    def args(self):
        """One-element tuple containing eigenstate label `j` that the projector
        projects onto"""
        return (self.j,)

    def _adjoint(self):
        return self


###############################################################################
# Algebra Operations
###############################################################################


class OperatorPlus(QuantumPlus, Operator):
    """A sum of Operators"""

    _neutral_element = ZeroOperator
    _binary_rules = OrderedDict()
    _simplifications = [
        assoc, scalars_to_op, orderby, filter_neutral,
        match_replace_binary]


class OperatorTimes(QuantumTimes, Operator):
    """A product of Operators that serves both as a product within a Hilbert
    space as well as a tensor product."""

    _neutral_element = IdentityOperator
    _binary_rules = OrderedDict()
    _simplifications = [assoc, orderby, filter_neutral, match_replace_binary]


class ScalarTimesOperator(Operator, ScalarTimesQuantumExpression):
    """Multiply an operator by a scalar coefficient."""

    _rules = OrderedDict()
    _simplifications = [match_replace, ]

    @staticmethod
    def has_minus_prefactor(c):
        """
        For a scalar object c, determine whether it is prepended by a "-" sign.
        """
        # TODO: check if this is necessary; if yes, move
        cs = str(c).strip()
        return cs[0] == "-"

    def _pseudo_inverse(self):
        c, t = self.operands
        return t.pseudo_inverse() / c

    def __eq__(self, other):
        # TODO: review, and add this to ScalarTimesQuantumExpression
        if self.term is IdentityOperator and is_scalar(other):
            return self.coeff == other
        return super().__eq__(other)

    def __hash__(self):
        # TODO: review, and add this to ScalarTimesQuantumExpression
        return super().__hash__()

    def _adjoint(self):
        return ScalarTimesOperator(self.coeff.conjugate(), self.term.adjoint())


class Commutator(QuantumOperation, Operator):
    r'''Commutator of two operators

    .. math::

        [\Op{A}, \Op{B}] = \Op{A}\Op{B} - \Op{A}\Op{B}

    '''

    _rules = OrderedDict()
    _simplifications = [
        scalars_to_op, disjunct_hs_zero, commutator_order, match_replace]
    # TODO: doit method

    order_key = FullCommutativeHSOrder

    # commutator_order makes FullCommutativeHSOrder anti-commutative

    def __init__(self, A, B):
        self._hs = A.space * B.space
        super().__init__(A, B)

    @property
    def A(self):
        """Left side of the commutator"""
        return self.operands[0]

    @property
    def B(self):
        """Left side of the commutator"""
        return self.operands[1]

    def _expand(self):
        A = self.A.expand()
        B = self.B.expand()
        if isinstance(A, OperatorPlus):
            A_summands = A.operands
        else:
            A_summands = (A,)
        if isinstance(B, OperatorPlus):
            B_summands = B.operands
        else:
            B_summands = (B,)
        summands = []
        for combo in cartesian_product(A_summands, B_summands):
            summands.append(Commutator.create(*combo))
        return OperatorPlus.create(*summands)

    def _series_expand(self, param, about, order):
        A_series = self.A.series_expand(param, about, order)
        B_series = self.B.series_expand(param, about, order)
        res = []
        for n in range(order + 1):
            summands = [self.create(A_series[k], B_series[n - k])
                        for k in range(n + 1)]
            res.append(OperatorPlus.create(*summands))
        return tuple(res)

    def _diff(self, sym):
        return (self.__class__(self.A.diff(sym), self.B) +
                self.__class__(self.A, self.B.diff(sym)))

    def _adjoint(self):
        return Commutator(self.B.adjoint(), self.A.adjoint())


class OperatorTrace(SingleQuantumOperation, Operator):
    r'''Take the (partial) trace of an operator `op` ($\Op{O}) over the degrees
    of freedom of a Hilbert space `over_space` ($\mathcal{H}$):

    .. math::

        {\rm Tr}_{\mathcal{H}} \Op{O}

    Args:
        over_space (.HilbertSpace): The degrees of freedom to trace over
        op (Operator): The operator to take the trace of.
    '''
    _rules = OrderedDict()
    _simplifications = [
        scalars_to_op, implied_local_space(keys=['over_space', ]),
        match_replace, ]

    def __init__(self, op, *, over_space):
        if isinstance(over_space, (int, str)):
            over_space = LocalSpace(over_space)
        assert isinstance(over_space, HilbertSpace)
        self._over_space = over_space
        super().__init__(op, over_space=over_space)
        self._space = None

    @property
    def kwargs(self):
        return {'over_space': self._over_space}

    @property
    def operand(self):
        return self.operands[0]

    @property
    def space(self):
        if self._space is None:
            return self.operands[0].space / self._over_space
        return self._space

    def _expand(self):
        s = self._over_space
        o = self.operand
        return OperatorTrace.create(o.expand(), over_space=s)

    def _series_expand(self, param, about, order):
        ope = self.operand.series_expand(param, about, order)
        return tuple(OperatorTrace.create(opet, over_space=self._over_space)
                     for opet in ope)

    def _diff(self, sym):
        s = self._over_space
        o = self.operand
        return OperatorTrace.create(o._diff(sym), over_space=s)

    def _adjoint(self):
        # there is a rule Tr[A^\dagger] -> Tr[A]^\dagger, which we don't want
        # to counteract here with an inverse rule
        return Adjoint(self)


class Adjoint(QuantumAdjoint, Operator):
    """The symbolic Adjoint of an operator."""

    _simplifications = [
        scalars_to_op, delegate_to_method('_adjoint')]

    def _pseudo_inverse(self):
        return self.operand.pseudo_inverse().adjoint()


class OperatorPlusMinusCC(SingleQuantumOperation, Operator):
    """An operator plus or minus its complex conjugate"""

    def __init__(self, op, *, sign=+1):
        self._sign = sign
        super().__init__(op, sign=sign)

    @property
    def kwargs(self):
        if self._sign > 0:
            return {'sign': +1, }
        else:
            return {'sign': -1, }

    @property
    def minimal_kwargs(self):
        if self._sign == +1:
            return {}
        else:
            return self.kwargs

    def _expand(self):
        return self

    def _pseudo_inverse(self):
        return OperatorPlusMinusCC(
            self.operand.pseudo_inverse(), sign=self._sign)

    def _diff(self, sym):
        return OperatorPlusMinusCC(
            self.operands._diff(sym), sign=self._sign)

    def _adjoint(self):
        return OperatorPlusMinusCC(self.operand.adjoint(), sign=self._sign)


class PseudoInverse(SingleQuantumOperation, Operator):
    r"""The symbolic pseudo-inverse :math:`X^+` of an operator :math:`X`. It is
    defined via the relationship

    .. math::

        X X^+ X =  X  \\
        X^+ X X^+ =  X^+  \\
        (X^+ X)^\dagger = X^+ X  \\
        (X X^+)^\dagger = X X^+
    """
    _rules = OrderedDict()
    _delegate_to_method = (ScalarTimesOperator, Squeeze, Displace,
                           ZeroOperator.__class__, IdentityOperator.__class__)
    _simplifications = [
        scalars_to_op, match_replace, delegate_to_method('_pseudo_inverse')]

    def _expand(self):
        return self

    def _pseudo_inverse(self):
        return self.operand

    def _adjoint(self):
        return Adjoint(self)


class NullSpaceProjector(SingleQuantumOperation, Operator):
    r"""Returns a projection operator :math:`\mathcal{P}_{{\rm Ker} X}` that
    projects onto the nullspace of its operand

    .. math::

        X \mathcal{P}_{{\rm Ker} X}
          = 0
        \Leftrightarrow
        X (1 - \mathcal{P}_{{\rm Ker} X})
          = X \\
        \mathcal{P}_{{\rm Ker} X}^\dagger
          = \mathcal{P}_{{\rm Ker} X}
          = \mathcal{P}_{{\rm Ker} X}^2
    """

    _rules = OrderedDict()
    _simplifications = [scalars_to_op, match_replace, ]

    def _expand(self):
        return self

    def _adjoint(self):
        return Adjoint(self)


class OperatorIndexedSum(QuantumIndexedSum, Operator):
    """Indexed sum over operators"""

    _rules = OrderedDict()
    _simplifications = [
        assoc_indexed, scalars_to_op, indexed_sum_over_kronecker,
        indexed_sum_over_const, match_replace, ]


###############################################################################
# Constructor Routines
###############################################################################


tr = OperatorTrace.create


def X(local_space, states=("h", "g")):
    r"""Pauli-type X-operator

    Args:
        local_space (.LocalSpace): Associated Hilbert space.
        states (tuple[int or str]): The qubit state labels for the basis states
            :math:`\left\{|0\rangle, |1\rangle \right\}`,
            where :math:`Z|0\rangle = +|0\rangle`, default = ``('h', 'g')``.

    Returns:
        Operator: Local X-operator as a linear combination of
        :class:`LocalSigma`
    """
    h, g = states  # TODO: default should be 0, 1
    return (
        LocalSigma.create(h, g, hs=local_space) +
        LocalSigma.create(g, h, hs=local_space))


def Y(local_space, states=("h", "g")):
    r""" Pauli-type Y-operator

    Args:
        local_space (LocalSpace): Associated Hilbert space.
        states (tuple[int or str]): The qubit state labels for the basis states
            :math:`\left\{|0\rangle, |1\rangle \right\}`,
            where :math:`Z|0\rangle = +|0\rangle`, default = ``('h', 'g')``.

    Returns:
        Operator: Local Y-operator as a linear combination of
        :class:`LocalSigma`

    """
    h, g = states
    return I * (-LocalSigma.create(h, g, hs=local_space) +
                LocalSigma.create(g, h, hs=local_space))


def Z(local_space, states=("h", "g")):
    r"""Pauli-type Z-operator

    Args:
        local_space (LocalSpace): Associated Hilbert space.
        states (tuple[int or str]): The qubit state labels for the basis states
            :math:`\left\{|0\rangle, |1\rangle \right\}`,
            where :math:`Z|0\rangle = +|0\rangle`, default = ``('h', 'g')``.

    Returns:
        Operator: Local Z-operator as a linear combination of
        :class:`LocalSigma`
    """
    h, g = states
    return (LocalProjector(h, hs=local_space) -
            LocalProjector(g, hs=local_space))


###############################################################################
# Auxilliary routines
###############################################################################


def factor_for_trace(ls: HilbertSpace, op: Operator) -> Operator:
    r'''Given a :class:`.LocalSpace` `ls` to take the partial trace over and an
    operator `op`, factor the trace such that operators acting on disjoint
    degrees of freedom are pulled out of the trace. If the operator acts
    trivially on ls the trace yields only a pre-factor equal to the dimension
    of ls. If there are :class:`LocalSigma` operators among a product, the
    trace's cyclical property is used to move to sandwich the full product by
    :class:`LocalSigma` operators:

    .. math::

        {\rm Tr} A \sigma_{jk} B = {\rm Tr} \sigma_{jk} B A \sigma_{jj}

    Args:
        ls: Degree of Freedom to trace over
        op: Operator to take the trace of

    Returns:
        The (partial) trace over the operator's spc-degrees of freedom
    '''
    if op.space == ls:
        if isinstance(op, OperatorTimes):
            pull_out = [o for o in op.operands if o.space is TrivialSpace]
            rest = [o for o in op.operands if o.space is not TrivialSpace]
            if pull_out:
                return (OperatorTimes.create(*pull_out) *
                        OperatorTrace.create(OperatorTimes.create(*rest),
                                             over_space=ls))
        raise CannotSimplify()
    if ls & op.space == TrivialSpace:
        return ls.dimension * op
    if ls < op.space and isinstance(op, OperatorTimes):
        pull_out = [o for o in op.operands if (o.space & ls) == TrivialSpace]

        rest = [o for o in op.operands if (o.space & ls) != TrivialSpace]
        if (not isinstance(rest[0], LocalSigma) or
            not isinstance(rest[-1], LocalSigma)):
            for j, r in enumerate(rest):
                if isinstance(r, LocalSigma):
                    m = r.j
                    rest = (
                        rest[j:] + rest[:j] +
                        [LocalSigma.create(m, m, hs=ls), ])
                    break
        if not rest:
            rest = [IdentityOperator]
        if len(pull_out):
            return (OperatorTimes.create(*pull_out) *
                    OperatorTrace.create(OperatorTimes.create(*rest),
                                         over_space=ls))
    raise CannotSimplify()


def decompose_space(H, A):
    """Simplifies OperatorTrace expressions over tensor-product spaces by
    turning it into iterated partial traces.

    Args:
        H (ProductSpace): The full space.
        A (Operator):

    Returns:
        Operator: Iterative partial trace expression
    """
    return OperatorTrace.create(
        OperatorTrace.create(A, over_space=H.operands[-1]),
        over_space=ProductSpace.create(*H.operands[:-1]))


def get_coeffs(expr, expand=False, epsilon=0.):
    """Create a dictionary with all Operator terms of the expression
    (understood as a sum) as keys and their coefficients as values.

    The returned object is a defaultdict that return 0. if a term/key
    doesn't exist.

    Args:
        expr: The operator expression to get all coefficients from.
        expand: Whether to expand the expression distributively.
        epsilon: If non-zero, drop all Operators with coefficients that have
            absolute value less than epsilon.

    Returns:
        dict: A dictionary ``{op1: coeff1, op2: coeff2, ...}``
    """
    if expand:
        expr = expr.expand()
    ret = defaultdict(int)
    operands = expr.operands if isinstance(expr, OperatorPlus) else [expr]
    for e in operands:
        c, t = _coeff_term(e)
        try:
            if abs(complex(c)) < epsilon:
                continue
        except TypeError:
            pass
        ret[t] += c
    return ret


def _coeff_term(op):
    # TODO: remove
    if isinstance(op, ScalarTimesOperator):
        return op.coeff, op.term
    elif is_scalar(op):
        if op == 0:
            return 0, ZeroOperator
        else:
            return op, IdentityOperator
    else:
        return 1, op


def factor_coeff(cls, ops, kwargs):
    """Factor out coefficients of all factors."""
    coeffs, nops = zip(*map(_coeff_term, ops))
    coeff = 1
    for c in coeffs:
        coeff *= c
    if coeff == 1:
        return nops, coeffs
    else:
        return coeff * cls.create(*nops, **kwargs)


def adjoint(obj):
    """Return the adjoint of an obj."""
    try:
        return obj.adjoint()
    except AttributeError:
        return obj.conjugate()


def Jpjmcoeff(ls, m, shift=False):
    r'''Eigenvalue of the $\Op{J}_{+}$ (:class:`Jplus`) operator, as a Sympy
    expression.

    .. math::

        \Op{J}_{+} \ket{s, m} = \sqrt{s (s+1) - m (m+1)} \ket{s, m}

    where the multiplicity $s$ is implied by the size of the Hilbert space
    `ls`: there are $2s+1$ eigenstates with $m = -s, -s+1, \dots, s$.

    Args:
        ls (LocalSpace): The Hilbert space in which the $\Op{J}_{+}$ operator
            acts.
        m (str or int): If str, the label of the basis state of `hs` to which
            the operator is applied. If integer together with ``shift=True``,
            the zero-based index of the basis state. Otherwise, directly the
            quantum number $m$.
        shift (bool): If True for a integer value of `m`, treat `m` as the
            zero-based index of the basis state (i.e., shift `m` down by $s$ to
            obtain the quantum number $m$)
    '''
    try:
        n = ls.dimension
        s = sympify(n - 1) / 2
        assert n == int(2 * s + 1)
        if isinstance(m, str):
            m = ls.basis_labels.index(m) - s  # m is now Sympy expression
        elif isinstance(m, int):
            if shift:
                assert 0 <= m < n
                m = m - s
        return sqrt(s * (s + 1) - m * (m + 1))
    except BasisNotSetError:
        raise CannotSimplify()


def Jzjmcoeff(ls, m, shift):
    r'''Eigenvalue of the $\Op{J}_z$ (:class:`Jz`) operator, as a Sympy
    expression.

    .. math::

        \Op{J}_{z} \ket{s, m} = m \ket{s, m}

    See also :func:`Jpjmcoeff`.
    '''
    try:
        n = ls.dimension
        s = sympify(n - 1) / 2
        assert n == int(2 * s + 1)
        if isinstance(m, str):
            return ls.basis.index(m) - s
        elif isinstance(m, int):
            if shift:
                assert 0 <= m < n
                return m - s
        else:
            return sympify(m)
    except BasisNotSetError:
        raise CannotSimplify()


def Jmjmcoeff(ls, m, shift):
    r'''Eigenvalue of the $\Op{J}_{-}$ (:class:`Jminus`) operator, as a Sympy
    expression

    .. math::

        \Op{J}_{-} \ket{s, m} = \sqrt{s (s+1) - m (m-1)} \ket{s, m}

    See also :func:`Jpjmcoeff`.
    '''
    try:
        n = ls.dimension
        s = sympify(n - 1) / 2
        assert n == int(2 * s + 1)
        if isinstance(m, str):
            m = ls.basis.index(m) - s  # m is now Sympy expression
        elif isinstance(m, int):
            if shift:
                assert 0 <= m < n
                m = m - s
        return sqrt(s * (s + 1) - m * (m - 1))
    except BasisNotSetError:
        raise CannotSimplify()


###############################################################################
# Extra ("manual") simplifications
###############################################################################


def _combine_operator_p_cc(A, B):
    if B.adjoint() == A:
        return OperatorPlusMinusCC(A, sign=+1)
    else:
        raise CannotSimplify


def _combine_operator_m_cc(A, B):
    if B.adjoint() == A:
        return OperatorPlusMinusCC(A, sign=-1)
    else:
        raise CannotSimplify


def _scal_combine_operator_pm_cc(c, A, d, B):
    if B.adjoint() == A:
        if c == d:
            return c * OperatorPlusMinusCC(A, sign=+1)
        elif c == -d:
            return c * OperatorPlusMinusCC(A, sign=-1)
    raise CannotSimplify


def create_operator_pm_cc():
    """Return a list of rules that can be used in an
    :func:`.extra_binary_rules` context for :class:`OperatorPlus` in order to
    combine suitable terms into a :class:`OperatorPlusMinusCC` instance::

        >>> A = OperatorSymbol('A', hs=1)
        >>> sum = A + A.dag()
        >>> with extra_binary_rules(OperatorPlus, create_operator_pm_cc()):
        ...     sum2 = sum.simplify()
        >>> print(ascii(sum2))
        A^(1) + c.c.

    The inverse is done through :func:`expand_operator_pm_cc`::

        >>> print(ascii(sum2.simplify(rules=expand_operator_pm_cc())))
        A^(1) + A^(1)H
    """
    A = wc("A", head=Operator)
    B = wc("B", head=Operator)
    c = wc("c", head=Scalar)
    d = wc("d", head=Scalar)
    return [
        ('pmCC1', (
            pattern_head(A, B),
            _combine_operator_p_cc)),
        ('pmCC2', (
            pattern_head(pattern(ScalarTimesOperator, -1, B), A),
            _combine_operator_m_cc)),
        ('pmCC3', (
            pattern_head(
                pattern(ScalarTimesOperator, c, A),
                pattern(ScalarTimesOperator, d, B)),
            _scal_combine_operator_pm_cc)),
    ]


def expand_operator_pm_cc():
    """Return a list of rules that can be used in `simplify` to expand
    instances of :class:`OperatorPlusMinusCC`

    Inverse of :func:`create_operator_pm_cc`.
    """
    # TODO: replace this functionality with a `doit` method
    A = wc("A", head=Operator)
    return OrderedDict([
        ('pmCCexpand1', (
            pattern(OperatorPlusMinusCC, A, sign=+1),
            lambda A: A + A.dag())),
        ('pmCCexpand2', (
            pattern(OperatorPlusMinusCC, A, sign=-1),
            lambda A: A - A.dag())),
    ])


Operator._zero = ZeroOperator
Operator._one = IdentityOperator
Operator._base_cls = Operator
Operator._scalar_times_expr_cls = ScalarTimesOperator
Operator._plus_cls = OperatorPlus
Operator._times_cls = OperatorTimes
Operator._adjoint_cls = Adjoint
Operator._indexed_sum_cls = OperatorIndexedSum
