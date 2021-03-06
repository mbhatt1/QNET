import unittest

from sympy import sqrt, exp, I, pi, Idx, IndexedBase, symbols, factorial

from qnet.algebra.core.abstract_algebra import simplify
from qnet.algebra.core.scalar_algebra import ScalarValue
from qnet.algebra.toolbox.core import no_rules
from qnet.algebra.core.operator_algebra import (
        OperatorSymbol, Create, Destroy, Jplus, Jminus, Jz, Phase, Displace,
        LocalSigma, IdentityOperator, OperatorPlus)
from qnet.algebra.core.hilbert_space_algebra import LocalSpace
from qnet.algebra.core.state_algebra import (
    KetSymbol, ZeroKet, KetPlus, ScalarTimesKet, CoherentStateKet,
    TrivialKet, TensorKet, BasisKet, KetBra, Bra, OperatorTimesKet, BraKet,
    KetBra, KetIndexedSum)
from qnet.algebra.core.exceptions import UnequalSpaces
from qnet.utils.indices import (
    IdxSym, FockIndex, IntIndex, StrLabel, SymbolicLabelBase,
    IndexOverFockSpace, IndexOverRange)
from qnet.algebra.pattern_matching import wc
import pytest


class TestStateAddition(unittest.TestCase):

    def testAdditionToZero(self):
        hs = LocalSpace("hs")
        a = KetSymbol("a", hs=hs)
        z = ZeroKet
        assert a+z == a
        assert z+a == a
        assert z+z == z
        assert z != 0
        assert z.is_zero

    def testAdditionToOperator(self):
        hs = LocalSpace("hs")
        a = KetSymbol("a", hs=hs)
        b = KetSymbol("b", hs=hs)
        assert a + b == b + a
        assert a + b == KetPlus(a,b)

    def testSubtraction(self):
        hs = LocalSpace("hs")
        a = KetSymbol("a", hs=hs)
        b = KetSymbol("b", hs=hs)
        z = ZeroKet
        lhs = a - a
        assert lhs == z
        lhs = a - b
        rhs = KetPlus(a, ScalarTimesKet(-1,b))
        assert lhs == rhs

    def testHilbertSpace(self):
        h1 = LocalSpace("h1")
        h2 = LocalSpace("h2")
        a = KetSymbol("a", hs=h1)
        b = KetSymbol("b", hs=h2)
        with pytest.raises(UnequalSpaces):
            a.__add__(b)

    def testEquality(self):
        h1 = LocalSpace("h1")
        assert (CoherentStateKet(10., hs=h1) + CoherentStateKet(20., hs=h1) ==
                CoherentStateKet(20., hs=h1) + CoherentStateKet(10., hs=h1))


class TestTensorKet(unittest.TestCase):

    def testIdentity(self):
        h1 = LocalSpace("h1")
        a = KetSymbol("a", hs=h1)
        id = TrivialKet
        assert a * id == a
        assert id * a == a

    def testOrdering(self):
        h1 = LocalSpace("h1")
        h2 = LocalSpace("h2")
        a = KetSymbol("a", hs=h1)
        b = KetSymbol("b", hs=h2)
        assert a * b == TensorKet(a,b)
        assert a * b == b * a

    def testHilbertSpace(self):
        h1 = LocalSpace("h1")
        h2 = LocalSpace("h2")
        a = KetSymbol("a", hs=h1)
        b = KetSymbol("b", hs=h2)
        assert a.space == h1
        assert (a * b).space == h1*h2

    def testEquality(self):
        h1 = LocalSpace("h1")
        h2 = LocalSpace("h2")

        assert (CoherentStateKet(1, hs=h1) * CoherentStateKet(2, hs=h2) ==
                CoherentStateKet(2, hs=h2) * CoherentStateKet(1, hs=h1))


class TestScalarTimesKet(unittest.TestCase):
    def testZeroOne(self):
        h1 = LocalSpace("h1")
        h2 = LocalSpace("h2")
        a = KetSymbol("a", hs=h1)
        b = KetSymbol("b", hs=h2)
        z = ZeroKet

        assert a+a == 2*a
        assert a*1 == a
        assert 1*a == a
        assert a*5 == ScalarTimesKet(5, a)
        assert 5*a == a*5
        assert 2*a*3 == 6*a
        assert a*5*b == ScalarTimesKet(5, a*b)
        assert a*(5*b) == ScalarTimesKet(5, a*b)

        assert 0 * a == z
        assert a * 0 == z
        assert 10 * z == z

    def testScalarCombination(self):
        a = KetSymbol("a", hs="h1")
        assert a+a == 2*a
        assert 3 * a + 4 * a == 7 * a
        assert (CoherentStateKet("1", hs=1) + CoherentStateKet("1", hs=1) ==
                2 * CoherentStateKet("1", hs=1))

    def testHilbertSpace(self):
        h1 = LocalSpace("h1")
        h2 = LocalSpace("h2")
        a = KetSymbol("a", hs=h1)
        b = KetSymbol("b", hs=h2)
        assert (5*(a * b)).space == h1*h2


class TestOperatorTimesKet(unittest.TestCase):

    def testZeroOne(self):
        h1 = LocalSpace("h1")
        h2 = LocalSpace("h2")
        a = KetSymbol("a", hs=h1)
        b = KetSymbol("b", hs=h2)
        A = OperatorSymbol("A", hs=h1)
        Ap = OperatorSymbol("Ap", hs=h1)
        B = OperatorSymbol("B", hs=h2)

        assert IdentityOperator*a == a
        assert A * (Ap * a) == (A * Ap) * a
        assert (A * B) * (a * b) == (A * a) * (B * b)

    def testScalarCombination(self):
        a = KetSymbol("a", hs="h1")
        assert a+a == 2*a
        assert 3 * a + 4 * a == 7 * a
        assert (CoherentStateKet("1", hs=1) + CoherentStateKet("1", hs=1) ==
                2 * CoherentStateKet("1", hs=1))

    def testHilbertSpace(self):
        h1 = LocalSpace("h1")
        h2 = LocalSpace("h2")
        a = KetSymbol("a", hs=h1)
        b = KetSymbol("b", hs=h2)
        assert (5*(a * b)).space == h1*h2


class TestLocalOperatorKetRelations(unittest.TestCase):

    def testCreateDestroy(self):
        assert Create(hs=1) * BasisKet(2, hs=1) == sqrt(3) * BasisKet(3, hs=1)
        assert Destroy(hs=1) * BasisKet(2, hs=1) == sqrt(2) * BasisKet(1, hs=1)
        assert Destroy(hs=1) * BasisKet(0, hs=1) == ZeroKet
        coh = CoherentStateKet(10., hs=1)
        a = Destroy(hs=1)
        lhs = a * coh
        rhs = 10 * coh
        assert lhs == rhs

    def testSpin(self):
        j = 3
        h = LocalSpace("j", basis=range(-j,j+1))

        assert (Jplus(hs=h) * BasisKet('2', hs=h) ==
                sqrt(j*(j+1)-2*(2+1)) * BasisKet('3', hs=h))
        assert (Jminus(hs=h) * BasisKet('2', hs=h) ==
                sqrt(j*(j+1)-2*(2-1)) * BasisKet('1', hs=h))
        assert Jz(hs=h) * BasisKet('2', hs=h) == 2 * BasisKet('2', hs=h)

    def testPhase(self):
        assert (Phase(5, hs=1) * BasisKet(3, hs=1) ==
                exp(I * 15) * BasisKet(3, hs=1))
        lhs = Phase(pi, hs=1) * CoherentStateKet(3., hs=1)
        rhs = CoherentStateKet(-3., hs=1)
        assert lhs.__class__ == rhs.__class__
        assert lhs.space == rhs.space
        assert abs(lhs.ampl - rhs.ampl) < 1e-14

    def testDisplace(self):
        assert (Displace(5 + 6j, hs=1) * CoherentStateKet(3., hs=1) ==
                exp(I * ((5+6j)*3).imag) * CoherentStateKet(8 + 6j, hs=1))
        assert (Displace(5 + 6j, hs=1) * BasisKet(0, hs=1) ==
                CoherentStateKet(5+6j, hs=1))

    def testLocalSigmaPi(self):
        assert (LocalSigma(0, 1, hs = 1) * BasisKet(1, hs=1) ==
                BasisKet(0, hs=1))
        assert (LocalSigma(0, 0, hs = 1) * BasisKet(1, hs=1) ==
                ZeroKet)

    def testActLocally(self):
        assert ((Create(hs=1) * Destroy(hs=2)) *
                (BasisKet(2, hs=1) * BasisKet(1, hs=2)) ==
                sqrt(3) * BasisKet(3, hs=1) * BasisKet(0, hs=2))


    def testOperatorTensorProduct(self):
        assert ((Create(hs=1)*Destroy(hs=2)) *
                (BasisKet(0, hs=1) * BasisKet(1, hs=2)) ==
                BasisKet(1, hs=1) * BasisKet(0, hs=2))

    def testOperatorProduct(self):
        assert ((Create(hs=1) * Destroy(hs=1)) *
                (BasisKet(1, hs=1) * BasisKet(1, hs=2)) ==
                BasisKet(1, hs=1) * BasisKet(1, hs=2))
        assert ((Create(hs=1) * Destroy(hs=1) * Destroy(hs=1)) *
                (BasisKet(2, hs=1)*BasisKet(1, hs=2)) ==
                sqrt(2) * BasisKet(1, hs=1) * BasisKet(1, hs=2))
        assert ((Create(hs=1) * Destroy(hs=1) * Destroy(hs=1)) *
                BasisKet(2, hs=1) ==
                sqrt(2) * BasisKet(1, hs=1))
        assert ((Create(hs=1) * Destroy(hs=1)) * BasisKet(1, hs=1) ==
                BasisKet(1, hs=1))
        assert ((Create(hs=1) * Destroy(hs=1)) * BasisKet(0, hs=1) == ZeroKet)


def test_expand_ketbra():
    """Test expansion of KetBra"""
    hs = LocalSpace('0', basis=('0', '1'))
    expr = KetBra(
        KetPlus(BasisKet('0', hs=hs), BasisKet('1', hs=hs)),
        KetPlus(BasisKet('0', hs=hs), BasisKet('1', hs=hs)))
    with no_rules(KetBra):
        expr_expand = expr.expand()
    assert expr_expand == OperatorPlus(
        KetBra(BasisKet('0', hs=hs), BasisKet('0', hs=hs)),
        KetBra(BasisKet('0', hs=hs), BasisKet('1', hs=hs)),
        KetBra(BasisKet('1', hs=hs), BasisKet('0', hs=hs)),
        KetBra(BasisKet('1', hs=hs), BasisKet('1', hs=hs)))


def eval_lb(expr, mapping):
    """Evaluate symbolic labels with the given mapping"""
    return simplify(expr, rules=[(
        wc('label', head=SymbolicLabelBase),
        lambda label: label.evaluate(mapping))])


def test_ket_symbolic_labels():
    """Test that we can instantiate Kets with symbolic labels"""
    i = Idx('i')
    i_sym = symbols('i')
    j = Idx('j')
    hs0 = LocalSpace(0)
    hs1 = LocalSpace(1)
    Psi = IndexedBase('Psi')

    assert (
        eval_lb(BasisKet(FockIndex(2 * i), hs=hs0), {i: 2}) ==
        BasisKet(4, hs=hs0))
    assert (
        eval_lb(BasisKet(FockIndex(2 * i_sym), hs=hs0), {i_sym: 2}) ==
        BasisKet(4, hs=hs0))
    with pytest.raises(TypeError) as exc_info:
        BasisKet(IntIndex(2 * i), hs=hs0)
    assert "not IntIndex" in str(exc_info.value)
    with pytest.raises(TypeError) as exc_info:
        BasisKet(StrLabel(2 * i), hs=hs0)
    assert "not StrLabel" in str(exc_info.value)
    with pytest.raises(TypeError) as exc_info:
        BasisKet(2 * i, hs=hs0)
    assert "not Mul" in str(exc_info.value)

    assert(
        eval_lb(KetSymbol(StrLabel(2 * i), hs=hs0), {i: 2}) ==
        KetSymbol("4", hs=hs0))
    with pytest.raises(TypeError) as exc_info:
        eval_lb(KetSymbol(FockIndex(2 * i), hs=hs0), {i: 2})
    assert "type of label must be str" in str(exc_info.value)

    assert StrLabel(Psi[i, j]).evaluate({i: 'i', j: 'j'}) == 'Psi_ij'
    assert(
        eval_lb(
            KetSymbol(StrLabel(Psi[i, j]), hs=hs0*hs1), {i: 'i', j: 'j'}) ==
        KetSymbol("Psi_ij", hs=hs0*hs1))
    assert(
        eval_lb(
            KetSymbol(StrLabel(Psi[i, j]), hs=hs0*hs1), {i: 1, j: 2}) ==
        KetSymbol("Psi_12", hs=hs0*hs1))

    assert (
        eval_lb(
            LocalSigma(FockIndex(i), FockIndex(j), hs=hs0), {i: 1, j: 2}) ==
        LocalSigma(1, 2, hs=hs0))
    assert (
        BasisKet(FockIndex(i), hs=hs0) * BasisKet(FockIndex(j), hs=hs0).dag() ==
        LocalSigma(FockIndex(i), FockIndex(j), hs=hs0))


def test_coherent_state_to_fock_representation():
    """Test the representation of a coherent state in the Fock basis"""
    alpha = symbols('alpha')

    expr1 = CoherentStateKet(alpha, hs=1).to_fock_representation()
    expr2 = CoherentStateKet(alpha, hs=1).to_fock_representation(max_terms=10)
    expr3 = CoherentStateKet(alpha, hs=1).to_fock_representation(
        index_symbol='i')
    expr4 = CoherentStateKet(alpha, hs=1).to_fock_representation(
        index_symbol=IdxSym('m', positive=True))

    assert (
        expr1.term.ranges[0] ==
        IndexOverFockSpace(IdxSym('n'), LocalSpace('1')))
    assert (
        expr2.term.ranges[0] ==
        IndexOverRange(IdxSym('n', integer=True), 0, 9))
    assert (
        expr3.term.ranges[0] ==
        IndexOverFockSpace(IdxSym('i'), LocalSpace('1')))
    assert (
        expr4.term.ranges[0] ==
        IndexOverFockSpace(IdxSym('m', positive=True), LocalSpace('1')))

    for expr in (expr1, expr2):
        assert expr.coeff == exp(-alpha*alpha.conjugate()/2)
        sum = expr.term
        assert len(sum.ranges) == 1
        n = sum.ranges[0].index_symbol
        assert sum.term.coeff == alpha**n/sqrt(factorial(n))
        assert (
            sum.term.term ==
            BasisKet(FockIndex(IdxSym('n')), hs=LocalSpace('1')))


def test_scalar_times_bra():
    """Test that multiplication of a scalar with a bra is handled correctly"""
    alpha_sym = symbols('alpha')
    alpha = ScalarValue(alpha_sym)
    ket = KetSymbol('Psi', hs=0)
    bra = ket.bra

    # first, let's try the ket case, just to establish a working baseline
    expr = alpha * ket
    assert expr == ScalarTimesKet(alpha, ket)
    assert expr == alpha_sym * ket
    assert isinstance((alpha_sym * ket).coeff, ScalarValue)
    assert expr == ket * alpha
    assert expr == ket * alpha_sym

    # now, the bra
    expr = alpha * bra
    assert expr == Bra(ScalarTimesKet(alpha.conjugate(), ket))
    assert expr == alpha_sym * bra
    assert isinstance((alpha_sym * bra).ket.coeff, ScalarValue)
    assert expr == bra * alpha
    assert expr == bra * alpha_sym


def test_disallow_inner_bra():
    """Test that it is not possible to instantiate a State Opereration that has
    a Bra as an operator: we accept Bra to be at the root of the expression
    tree"""
    alpha = symbols('alpha')
    A = OperatorSymbol('A', hs=0)
    ket1 = KetSymbol('Psi_1', hs=0)
    ket2 = KetSymbol('Psi_1', hs=0)
    bra1 = Bra(ket1)
    bra2 = Bra(ket2)
    bra1_hs1 = Bra(KetSymbol('Psi_1', hs=1))

    with pytest.raises(TypeError) as exc_info:
        KetPlus(bra1, bra2)
    assert "must be Kets" in str(exc_info.value)
    assert isinstance(KetPlus.create(bra1, bra2), Bra)

    with pytest.raises(TypeError) as exc_info:
        TensorKet(bra1, bra1_hs1)
    assert "must be Kets" in str(exc_info.value)
    assert isinstance(TensorKet.create(bra1, bra1_hs1), Bra)

    with pytest.raises(TypeError) as exc_info:
        ScalarTimesKet(alpha, bra1)
    assert "must be Kets" in str(exc_info.value)
    assert isinstance(ScalarTimesKet.create(alpha, bra1), Bra)

    with pytest.raises(TypeError) as exc_info:
        OperatorTimesKet(A, bra1)
    assert "must be Kets" in str(exc_info.value)
    with pytest.raises(TypeError) as exc_info:
        OperatorTimesKet(bra1, A)
    assert "must be Kets" in str(exc_info.value)

    with pytest.raises(TypeError) as exc_info:
        BraKet(bra1, ket2)
    assert "must be Kets" in str(exc_info.value)

    with pytest.raises(TypeError) as exc_info:
        KetBra(ket1, bra2)
    assert "must be Kets" in str(exc_info.value)

    i = IdxSym('i')
    Psi = IndexedBase('Psi')
    psi_i = KetSymbol(StrLabel(Psi[i]), hs=0)
    with pytest.raises(TypeError) as exc_info:
        KetIndexedSum(Bra(psi_i), IndexOverFockSpace(i, hs=0))
    assert "must be Kets" in str(exc_info.value)
    assert isinstance(
        KetIndexedSum.create(Bra(psi_i), IndexOverFockSpace(i, hs=0)),
        Bra)
