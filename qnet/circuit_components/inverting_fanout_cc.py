#!/usr/bin/env python
# encoding: utf-8
#This file was automatically created using QNET.

"""
inverting_fanout_cc.py

Created automatically by $QNET/bin/parse_qhdl.py
Get started by instantiating a circuit instance via:

    >>> InvertingFanout()

"""

__all__ = ['InvertingFanout']

from qnet.circuit_components.library import make_namespace_string
from qnet.circuit_components.component import Component
from qnet.algebra.circuit_algebra import cid, P_sigma, FB, SLH
import unittest
from sympy import symbols
from qnet.circuit_components.three_port_kerr_cavity_cc import ThreePortKerrCavity
from qnet.circuit_components.beamsplitter_cc import Beamsplitter
from qnet.circuit_components.displace_cc import Displace
from qnet.circuit_components.phase_cc import Phase



class InvertingFanout(Component):

    # total number of field channels
    CDIM = 5
    
    # parameters on which the model depends
    Delta = 50.0
    chi = -0.14
    kappa_1 = 20.0
    kappa_2 = 20.0
    kappa_3 = 10.0
    theta = 0.473
    phi = -1.45
    alpha = -130.0
    _parameters = ['Delta', 'alpha', 'chi', 'kappa_1', 'kappa_2', 'kappa_3', 'phi', 'theta']

    # list of input port names
    PORTSIN = ['In1']
    
    # list of output port names
    PORTSOUT = ['Out1', 'Out2']

    # sub-components
    
    @property
    def B1(self):
        return Beamsplitter(make_namespace_string(self.name, 'B1'))

    @property
    def B2(self):
        return Beamsplitter(make_namespace_string(self.name, 'B2'), theta = self.theta)

    @property
    def B3(self):
        return Beamsplitter(make_namespace_string(self.name, 'B3'))

    @property
    def C(self):
        return ThreePortKerrCavity(make_namespace_string(self.name, 'C'), kappa_2 = self.kappa_2, chi = self.chi, kappa_1 = self.kappa_1, kappa_3 = self.kappa_3, Delta = self.Delta)

    @property
    def Phase(self):
        return Phase(make_namespace_string(self.name, 'Phase'), phi = self.phi)

    @property
    def W(self):
        return Displace(make_namespace_string(self.name, 'W'), alpha = self.alpha)

    _sub_components = ['B1', 'B2', 'B3', 'C', 'Phase', 'W']
    

    def _toSLH(self):
        return self.creduce().toSLH()
        
    def _creduce(self):

        B1, B2, B3, C, Phase, W = self.B1, self.B2, self.B3, self.C, self.Phase, self.W

        return P_sigma(0, 1, 2, 4, 3) << (((((B3 + cid(1)) << P_sigma(0, 2, 1) << (B2 + cid(1))) + cid(1)) << P_sigma(0, 1, 3, 2) << (((Phase + cid(2)) << P_sigma(1, 0, 2) << C) + cid(1))) + cid(1)) << P_sigma(0, 4, 1, 2, 3) << ((P_sigma(1, 0) << B1 << (W + cid(1))) + cid(3)) << P_sigma(1, 0, 4, 2, 3)

    @property
    def _space(self):
        return self.creduce().space


# Test the circuit
class TestInvertingFanout(unittest.TestCase):
    """
    Automatically created unittest test case for InvertingFanout.
    """

    def testCreation(self):
        a = InvertingFanout()
        self.assertIsInstance(a, InvertingFanout)

    def testCReduce(self):
        a = InvertingFanout().creduce()

    def testParameters(self):
        if len(InvertingFanout._parameters):
            pname = InvertingFanout._parameters[0]
            obj = InvertingFanout(name="TestName", namespace="TestNamespace", **{pname: 5})
            self.assertEqual(getattr(obj, pname), 5)
            self.assertEqual(obj.name, "TestName")
            self.assertEqual(obj.namespace, "TestNamespace")

        else:
            obj = InvertingFanout(name="TestName", namespace="TestNamespace")
            self.assertEqual(obj.name, "TestName")
            self.assertEqual(obj.namespace, "TestNamespace")

    def testToSLH(self):
        aslh = InvertingFanout().toSLH()
        self.assertIsInstance(aslh, SLH)

if __name__ == "__main__":
    unittest.main()