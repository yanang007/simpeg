from __future__ import print_function
import unittest
import numpy as np

import SimPEG.electromagnetics.time_domain as tdem
from SimPEG import *
from discretize import TensorMesh
from pymatsolver import PardisoSolver

np.random.seed(41)


class GlobalEM1DTD(unittest.TestCase):

    def setUp(self, parallel=True):

        times_hm = np.logspace(-6, -3, 31)
        times_lm = np.logspace(-5, -2, 31)

        # Waveforms
        waveform_hm = tdem.sources.TriangularWaveform(
            start_time=-0.01, peak_time=-0.005, off_time=0.0
        )
        waveform_lm = tdem.sources.TriangularWaveform(
            start_time=-0.01, peak_time=-0.0001, off_time=0.0
        )

        dz = 1
        geometric_factor = 1.1
        n_layer = 20
        thicknesses = dz * geometric_factor ** np.arange(n_layer-1)
        n_layer = 20

        n_sounding = 5
        dx = 20.
        hx = np.ones(n_sounding) * dx
        hz = np.r_[thicknesses, thicknesses[-1]]
        mesh = TensorMesh([hx, hz], x0='00')
        inds = mesh.gridCC[:, 1] < 25
        inds_1 = mesh.gridCC[:, 1] < 50
        sigma = np.ones(mesh.nC) * 1./100.
        sigma[inds_1] = 1./10.
        sigma[inds] = 1./50.
        sigma_em1d = sigma.reshape(mesh.vnC, order='F').flatten()
        mSynth = np.log(sigma_em1d)

        x = mesh.vectorCCx
        y = np.zeros_like(x)
        z = np.ones_like(x) * 30.
        source_locations = np.c_[x, y, z]
        source_current = 1.
        source_orientation = 'z'
        source_radius = 10.

        receiver_offset_r = 13.25
        receiver_offset_z = 2.

        receiver_locations = np.c_[x+receiver_offset_r, np.zeros(n_sounding), 30.*np.ones(n_sounding)+receiver_offset_z]
        receiver_orientation = "z"  # "x", "y" or "z"

        topo = np.c_[x, y, z-30.].astype(float)

        sigma_map = maps.ExpMap(mesh)

        source_list = []

        for i_sounding in range(0, n_sounding):

            source_location = source_locations[i_sounding, :]
            receiver_location = receiver_locations[i_sounding, :]

            # Receiver list

            # Define receivers at each location.
            dbzdt_receiver_hm = tdem.receivers.PointMagneticFluxTimeDerivative(
                receiver_location, times_hm, receiver_orientation
            )
            dbzdt_receiver_lm = tdem.receivers.PointMagneticFluxTimeDerivative(
                receiver_location, times_lm, receiver_orientation
            )
            # Make a list containing all receivers even if just one

            # Must define the transmitter properties and associated receivers
            source_list.append(tdem.sources.MagDipole(
                [dbzdt_receiver_hm],
                location=source_location,
                waveform=waveform_hm,
                orientation=source_orientation,
                i_sounding=i_sounding,
            )
            )

            source_list.append(tdem.sources.MagDipole(
                [dbzdt_receiver_lm],
                location=source_location,
                waveform=waveform_lm,
                orientation=source_orientation,
                i_sounding=i_sounding,
            )
            )


        survey = tdem.Survey(source_list)

        simulation = tdem.Simulation1DLayeredStitched(
            survey=survey, thicknesses=thicknesses, sigmaMap=sigma_map,
            topo=topo, parallel=False, n_cpu=2, verbose=False, solver=PardisoSolver
        )

        dpred = simulation.dpred(mSynth)
        noise = 0.1*np.abs(dpred)*np.random.rand(len(dpred))
        uncertainties = 0.1*np.abs(dpred)*np.ones(np.shape(dpred))
        dobs =  dpred + noise
        data_object = data.Data(survey, dobs=dobs, noise_floor=uncertainties)

        dmis = data_misfit.L2DataMisfit(simulation=simulation, data=data_object)
        dmis.W = 1./uncertainties

        reg = regularization.Tikhonov(mesh)

        opt = optimization.InexactGaussNewton(
            maxIterLS=20, maxIter=10, tolF=1e-6,
            tolX=1e-6, tolG=1e-6, maxIterCG=6
        )

        invProb = inverse_problem.BaseInvProblem(dmis, reg, opt, beta=0.)
        inv = inversion.BaseInversion(invProb)

        self.data = data_object
        self.dmis = dmis
        self.inv = inv
        self.reg = reg
        self.sim = simulation
        self.mesh = mesh
        self.m0 = mSynth
        self.survey = survey


    def test_misfit(self):
        passed = tests.checkDerivative(
            lambda m: (
                self.sim.dpred(m),
                lambda mx: self.sim.Jvec(self.m0, mx)
            ),
            self.m0,
            plotIt=False,
            num=3
        )
        self.assertTrue(passed)

    def test_adjoint(self):
        # Adjoint Test
        v = np.random.rand(self.mesh.nC)
        w = np.random.rand(self.data.dobs.shape[0])
        wtJv = w.dot(self.sim.Jvec(self.m0, v))
        vtJtw = v.dot(self.sim.Jtvec(self.m0, w))
        passed = np.abs(wtJv - vtJtw) < 1e-10
        print('Adjoint Test', np.abs(wtJv - vtJtw), passed)
        self.assertTrue(passed)

    def test_dataObj(self):
        passed = tests.checkDerivative(
            lambda m: [self.dmis(m), self.dmis.deriv(m)],
            self.m0,
            plotIt=False,
            num=3
        )
        self.assertTrue(passed)

if __name__ == '__main__':
    unittest.main()