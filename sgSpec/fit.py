from __future__ import division
from builtins import zip
from builtins import range
from builtins import object
import numpy as np
from .gaussian import *
from scipy.optimize import curve_fit
import emcee
import corner
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.cm as cm
import six

__all__ = ["Fit_Double_Gaussian", "Fit_Gaussian_DoublePeak", "SpectraFitter"]

def Fit_Gaussian_DoublePeak(x, y, **curve_fit_kws):
    """
    Fit the data with a Gaussian Double Peak profile.

    The model parameters are:
        x : 1D array
            The variable of the function.  It should be monochromatically increasing.
        ag : float
            The peak flux of the two half-Gaussians.  Require ag > 0.
        ac : float
            The flux at the central velocity.  Require ac > 0.
        v0 : float
            The center of the profile.
        sigma : float
            The standard deviation of the half-Gaussian profile.  Require sigma > 0.
        w : float
            The half-width of the central parabola.  Require w > 0.

    Parameters
    ----------
    x : array like
        The variable of the data.
    y : array like
        The dependant variable of the data.
    **curve_fit_kws : (optional)
        Additional parameters for curve_fit.

    Returns
    -------
    popt : array
        The best-fit parameters.
    perr : array
        The errors of the best-fit parameters.
    """
    popt, pcov = curve_fit(Gaussian_DoublePeak, x, y, **curve_fit_kws)
    perr = np.sqrt(np.diag(pcov))
    return popt, perr

def Fit_Double_Gaussian(x, y, **curve_fit_kws):
    """
    Fit the data with a double-peaked Gaussian profile.

    The model parameters are:
        x : array like
            The variable of the data.
        a1, b1, c1 : float
            The amplitude, mean and standard deviation of the first Gaussian component.
        a2, b2, c2 : float
            The amplitude, mean and standard deviation of the first Gaussian component.

    Parameters
    ----------
    x : array like
        The variable of the data.
    y : array like
        The dependant variable of the data.
    **curve_fit_kws : (optional)
        Additional parameters for curve_fit.

    Returns
    -------
    popt : array
        The best-fit parameters.
    perr : array
        The errors of the best-fit parameters.
    """
    popt, pcov = curve_fit(Double_Gaussian, x, y, **curve_fit_kws)
    perr = np.sqrt(np.diag(pcov))
    return popt, perr

class SpectraFitter(object):
    """
    The mcmc fitter of spectra.
    """
    def __init__(self, function, prior_list, x, y, yerr):
        """
        Parameters
        ----------
        function : function
            The model function.
        prior_list : list
            The list of prior constrains.  Use {0[i]} to represent the ith parameter.
            Example:
                "({0[2]} > -500) & ({0[2]} < 500)" means the 3rd parameter larger than -500 and smaller than 500.
        x : 1D array
            The variable of the spectrum.
        y : 1D array
            The flux of the spectrum.
        yerr : float or 1D array
            The uncertainty of the spectrum.
        """
        self.function = function
        self.prlist = prior_list
        self.x = x
        self.y = y
        self.yerr = yerr
        self.ndim = None # Asigned after fitting
        self.sampler = None # Asigned after fitting

    def fit(self, p0, nwalkers, steps, p_rad=1e-4):
        """
        Fit the data with given initial guess and nwalkers.

        Parameters
        ----------
        p0 : list
            The initial guess.
        nwalkers : int
            The number of walkers.
        steps : int
            The number of steps.
        p_rad : float, default: 1e-4
            The fraction to perturbe the parameters around p0, in order to
            generate the initial position of all the walkers.

        Returns
        -------
        sampler : EnsembleSampler
            The sampler after the mcmc run.
        """
        ndim = len(p0)
        self.ndim = ndim
        pos = [np.array(p0) + 1e-4*np.random.randn(ndim) for i in range(nwalkers)]
        sampler = emcee.EnsembleSampler(nwalkers, ndim, self.lnprob)
        sampler.run_mcmc(pos, steps)
        self.sampler = sampler
        return sampler

    def get_samples(self, burnin):
        """
        Get the marginalized samples.
        """
        assert type(burnin) is int
        samples = self.sampler.chain[:, burnin:, :].reshape((-1, self.ndim))
        return samples

    def get_bestfit(self, burnin, percList=None, nsample=None, qfunction=None, qf_args=[]):
        """
        Get the best-fit results.

        Parameters
        ----------
        burnin : float
            The lenght of the burnin chain.
        percList : list
            The lower, median, and upper percentiles to calculate the best fit and
            uncertainties.
        nsample : int (optional)
            The number of sampled parameters that are randomly selected to calculate
            the best-fit values.  By default, all of the mcmc samples, besides the
            burnin chains, are used.
        qfunction : function (optional)
            The function to calculate the best-fit quanties and the errors based
            on the mcmc sampled parameters.  Usage:
                qfunction(samples, *qf_args)
        qf_args : list
            The additional arguments of qfunction.

        Returns
        -------
        If quant_expr is not provided, it returns the best-fit parameters of the
        model, list of tuples of (median, upper error, lower error).

        Otherwise, it calculates the requested quanty based on the mcmc samples,
        and returns the tuple of (median, upper error, lower error) from the mcmc
        samples.
        """
        samples = self.get_samples(burnin)
        lsample = samples.shape[0]
        if nsample is None:
            nsample = lsample # Use all of the samples
        sList = []
        for idx in np.random.randint(0, lsample, nsample):
            sList.append(samples[idx, :])
        sList = np.array(sList)
        if percList is None:
            percList = [16, 50, 84]
        if qfunction is None:
            v = np.percentile(sList, percList, axis=0)
            results = [(v[1], v[2]-v[1], v[1]-v[0]) for v in zip(*v)]
        else:
            quant = np.array(qfunction(sList, *qf_args))
            if len(quant.shape) == 1:
                v = np.percentile(quant, percList)
                results = (v[1], v[2]-v[1], v[1]-v[0])
            else:
                v = np.percentile(quant, percList, axis=0)
                results = [(v[1], v[2]-v[1], v[1]-v[0]) for v in zip(*v)]
        return results

    def plot_corner(self, burnin, **kwargs):
        """
        Generate the corner plot.
        """
        samples = self.get_samples(burnin)
        fig = corner.corner(samples, **kwargs)
        return fig

    def plot_trace(self, burnin, names):
        "Plot trace of MCMC walkers"

        ######################################
        # Setup plot:
        f = plt.figure()
        scale = 1.75
        nRows = len(names)
        nWalkers = self.sampler.chain.shape[0]

        f.set_size_inches(4.*scale, nRows*scale)
        gs = gridspec.GridSpec(nRows, 1, hspace=0.2)

        axes = []
        alpha = max(0.01, 1./nWalkers)

        # Define random color inds for tracking some walkers:
        nTraceWalkers = 5
        cmap = cm.viridis
        alphaTrace = 0.8
        lwTrace = 1.5
        trace_inds = np.random.randint(0, nWalkers, size=nTraceWalkers)
        trace_colors = []
        for i in six.moves.xrange(nTraceWalkers):
            trace_colors.append(cmap(1./np.float(nTraceWalkers)*i))

        norm_inds = np.setdiff1d(range(nWalkers), trace_inds)

        for k in six.moves.xrange(nRows):
            axes.append(plt.subplot(gs[k,0]))

            axes[k].plot(self.sampler.chain[norm_inds, burnin:, k].T, '-', color='black', alpha=alpha)

            for j in six.moves.xrange(nTraceWalkers):
                axes[k].plot(self.sampler.chain[trace_inds[j], burnin:, k].T, '-',
                             color=trace_colors[j], lw=lwTrace, alpha=alphaTrace)

            axes[k].set_ylabel(names[k])

            if k == nRows-1:
                axes[k].set_xlabel('Step number')
            else:
                axes[k].set_xticks([])

        return axes, f

    def get_sampler(self):
        """
        Get the current sampler.
        """
        return self.sampler

    def chisq(self, theta):
        """
        Calculate the chi square.
        """
        m = self.function(self.x, *theta)
        csq = np.sum( ((self.y - m)/self.yerr)**2. )
        return csq

    def chisq_rd(self, theta):
        """
        Calculate the reduced chi square.
        """
        dof = len(self.x) - len(theta)
        csq_rd = self.chisq(theta) / dof
        return csq_rd

    def lnlike(self, theta):
        """
        Likelihood function.
        """
        #m = self.function(self.x, *theta)
        #chisq = np.sum( ((self.y - m)/self.yerr)**2. )
        lnl = -0.5 * self.chisq(theta)
        return lnl

    def lnprior(self, theta):
        """
        Prior function.
        """
        flag = True
        for pr in self.prlist:
            flag = flag & eval(pr.format(theta))
        if flag:
            return 0.0
        return -np.inf

    def lnprob(self, theta):
        """
        Probability function.
        """
        lp = self.lnprior(theta)
        if not np.isfinite(lp):
            return -np.inf
        return lp + self.lnlike(theta)
