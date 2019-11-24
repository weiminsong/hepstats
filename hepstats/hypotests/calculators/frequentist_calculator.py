import numpy as np
from scipy.stats import norm
from collections import OrderedDict

from .basecalculator import BaseCalculator
from ..fitutils.utils import pll, get_nevents
from ..fitutils.sampling import base_sampler, base_sample
from ..parameters import POI, POIarray


class FrequentistCalculator(BaseCalculator):
    """
    Class for frequentist calculators.
    """

    def __init__(self, input, minimizer, ntoysnull=100, ntoysalt=100, sampler=base_sampler, sample=base_sample):
        """Frequentist calculator class.

            Args:
                input : loss or fit result
                minimizer : minimizer to use to find the minimum of the loss function
                ntoysnull (int, optionnal): number of toys to generate for the null hypothesis
                ntoysalt (int, optionnal): number of toys to generate for the alternative hypothesis

            Example with `zfit`:
                >>> import zfit
                >>> from zfit.core.loss import UnbinnedNLL
                >>> from zfit.minimize import MinuitMinimizer

                >>> obs = zfit.Space('x', limits=(0.1, 2.0))
                >>> data = zfit.data.Data.from_numpy(obs=obs, array=np.random.normal(1.2, 0.1, 10000))
                >>> mean = zfit.Parameter("mu", 1.2)
                >>> sigma = zfit.Parameter("sigma", 0.1)
                >>> model = zfit.pdf.Gauss(obs=obs, mu=mean, sigma=sigma)
                >>> loss = UnbinnedNLL(model=[model], data=[data], fit_range=[obs])

                >>> calc = FrequentistCalculator(input=loss, minimizer=MinuitMinimizer(), ntoysnull=1000, ntoysalt=1000)
        """

        super(FrequentistCalculator, self).__init__(input, minimizer)

        self._toysnull = {}
        self._toysalt = {}
        self._ntoysnull = ntoysnull
        self._ntoysalt = ntoysalt
        self._sampler = sampler
        self._sample = sample
        self._toys_loss = {}
        self._printlevel = 1

    @property
    def ntoysnull(self):
        return self._ntoysnull

    @property
    def ntoysalt(self):
        return self._ntoysalt

    @property
    def printlevel(self):
        return self._printlevel

    def sampler(self, floatting_params=None, *args, **kwargs):
        self.set_dependents_to_bestfit()
        nevents = []
        for m, d in zip(self.model, self.data):
            if m.is_extended:
                nevents.append("extended")
            else:
                nevents.append(get_nevents(d))

        return self._sampler(self.model,  nevents, floatting_params, *args, **kwargs)

    def sample(self, sampler, ntoys, param=None, value=None):
        return self._sample(sampler, ntoys, param, value)

    def toys_loss(self, parameter):
        if parameter.name not in self._toys_loss:
            sampler = self.sampler(floatting_params=[parameter])
            self._toys_loss[parameter.name] = self.lossbuilder(self.model, sampler)
        return self._toys_loss[parameter.name]

    def _generate_and_fit_toys(self, poigen, ntoys, poieval, printfreq=0.2):
        minimizer = self.minimizer

        param = poigen.parameter
        gen_value = poigen.value

        toys_loss = self.toys_loss(param)
        sampler = toys_loss.data

        result = {"bestfit": {"values": np.empty(ntoys), "nll": np.empty(ntoys)},
                  "nll": {p: np.empty(ntoys) for p in poieval}}

        printfreq = ntoys * printfreq

        toys = self.sample(sampler, int(ntoys*1.2), param, gen_value)

        for i in range(ntoys):
            converged = False
            toprint = i % printfreq == 0
            while converged is False:
                try:
                    next(toys)
                except StopIteration:
                    to_gen = ntoys - i
                    toys = self.sample(sampler, int(to_gen*1.2), param, gen_value)
                    next(toys)

                minimum = minimizer.minimize(loss=toys_loss)
                converged = minimum.converged

                if not converged:
                    self.set_dependents_to_bestfit()
                    continue

                bestfit = minimum.params[param]["value"]
                result["bestfit"]["values"][i] = bestfit
                nll = pll(minimizer, toys_loss, POI(param, bestfit))
                result["bestfit"]["nll"][i] = nll

                for p in poieval:
                    nll = pll(minimizer, toys_loss, p)
                    result["nll"][p][i] = nll

            if toprint:
                print("{0} toys generated, fitted and scanned!".format(i))

            if i > ntoys:
                break
            i += 1

        return result

    def _gettoys(self, poigen, poieval=None, qtilde=False, hypotesis="null"):

        assert hypotesis in ["null", "alternative"]

        if hypotesis == "null":
            ntoys = self.ntoysnull
            toysdict = self._toysnull
        else:
            ntoys = self.ntoysalt
            toysdict = self._toysalt

        for p in poigen:
            if p not in toysdict:
                ntogen = ntoys
            else:
                ngenerated = toysdict[p]["bestfit"]["values"].size
                if ngenerated < ntoys:
                    ntogen = ntoys - ngenerated
                else:
                    ntogen = 0

            if ntogen > 0:
                if self.printlevel >= 0:
                    print(f"Generating {hypotesis} hypothesis toys for {p}.")

                eval_values = [p.value]
                if qtilde:
                    eval_values.append(0.)
                if poieval:
                    eval_values += poieval.values.tolist()
                eval_values = list(dict.fromkeys(eval_values))

                toyresult = self._generate_and_fit_toys(p, ntogen, POIarray(poigen.parameter, eval_values))

                if p in toysdict:
                    toysdict[p].update(toyresult)
                else:
                    toysdict[p] = toyresult

        return {p: toysdict[p] for p in poigen}

    def gettoys_null(self, poigen, poieval=None, qtilde=False):
        return self._gettoys(poigen=poigen, poieval=poieval, qtilde=qtilde, hypotesis="null")

    def gettoys_alt(self, poigen, poieval=None, qtilde=False):
        return self._gettoys(poigen=poigen, poieval=poieval, qtilde=qtilde, hypotesis="alternative")

    def qnull(self, poinull, poialt, onesided, onesideddiscovery, qtilde=False):
        toysresults = self.gettoys_null(poinull, poialt, qtilde)
        ret = {}

        for p in poinull:
            toysresult = toysresults[p]
            nll1 = toysresult["nll"][p]
            nll2 = toysresult["bestfit"]["nll"]
            bestfit = toysresult["bestfit"]["values"]

            if qtilde:
                nllat0 = toysresult["nll"][0]
                nll2 = np.where(bestfit < 0, nllat0, nll2)
                bestfit = np.where(bestfit < 0, 0, bestfit)

            poi1 = POIarray(poinull.parameter, np.full(self.ntoysnull, p.value))
            poi2 = POIarray(poinull.parameter, bestfit)

            ret[p] = self.q(nll1=nll1, nll2=nll2, poi1=poi1, poi2=poi2, onesided=onesided,
                            onesideddiscovery=onesideddiscovery)

        return ret

    def qalt(self, poinull, poialt, onesided, onesideddiscovery, qtilde=False):
        toysresults = self.gettoys_alt(poialt, poinull, qtilde)
        ret = {}

        for p in poinull:
            toysresult = toysresults[poialt]

            nll1 = toysresult["nll"][p]
            nll2 = toysresult["bestfit"]["nll"]
            bestfit = toysresult["bestfit"]["values"]

            if qtilde:
                nllat0 = toysresult["nll"][0]
                nll2 = np.where(bestfit < 0, nllat0, nll2)
                bestfit = np.where(bestfit < 0, 0, bestfit)

            poi1 = POIarray(poialt.parameter, np.full(self.ntoysalt, p.value))
            poi2 = POIarray(poialt.parameter, bestfit)

            ret[p] = self.q(nll1=nll1, nll2=nll2, poi1=poi1, poi2=poi2, onesided=onesided,
                            onesideddiscovery=onesideddiscovery)

        return ret

    def _pvalue_(self, poinull, poialt, qtilde, onesided, onesideddiscovery):

        qobs = self.qobs(poinull, onesided=onesided, qtilde=qtilde,
                         onesideddiscovery=onesideddiscovery)

        def compute_pvalue(qdist, qobs):
            qdist = qdist[~(np.isnan(qdist) | np.isinf(qdist))]
            p = len(qdist[qdist >= qobs])/len(qdist)
            return p

        qnulldist = self.qnull(poinull, poialt, onesided, onesideddiscovery, qtilde)
        pnull = np.empty(len(poinull))
        for i, p in enumerate(poinull):
            pnull[i] = compute_pvalue(qnulldist[p], qobs[i])

        if poialt is not None:
            qaltdist = self.qalt(poinull, poialt, onesided, onesideddiscovery, qtilde)
            palt = np.empty(len(poinull))
            for i, p in enumerate(poinull):
                palt[i] = compute_pvalue(qaltdist[p], qobs[i])
        else:
            palt = None

        return pnull, palt

    def _expected_pvalue_(self, poinull, poialt, nsigma, CLs, onesided, onesideddiscovery, qtilde):

        ps = {ns: {"p_clsb": np.empty(len(poinull)),
                   "p_clb": np.empty(len(poinull))} for ns in nsigma}

        qnulldist = self.qnull(poinull, poialt, onesided, onesideddiscovery, qtilde)
        qaltdist = self.qalt(poinull, poialt, onesided, onesideddiscovery, qtilde)

        filter_nan = lambda q: q[~(np.isnan(q) | np.isinf(q))]

        for i, p in enumerate(poinull):

            qaltdist_p = filter_nan(qaltdist[p])
            lqaltdist = len(qaltdist_p)

            qnulldist_p = filter_nan(qnulldist[p])
            lqnulldist = len(qnulldist_p)

            p_clsb_i = np.empty(lqaltdist)
            p_clb_i = np.empty(lqaltdist)

            for j, q in np.ndenumerate(qaltdist_p):
                p_clsb_i[j] = (len(qnulldist_p[qnulldist_p >= q])/lqnulldist)
                p_clb_i[j] = (len(qaltdist_p[qaltdist_p >= q])/lqaltdist)

            for ns in nsigma:
                frac = norm.cdf(ns)*100
                ps[ns]["p_clsb"][i] = np.percentile(p_clsb_i, frac)
                ps[ns]["p_clb"][i] = np.percentile(p_clb_i, frac)

        expected_pvalues = []
        for ns in nsigma:
            if CLs:
                p_cls = ps[ns]["p_clsb"] / ps[ns]["p_clb"]
                expected_pvalues.append(np.where(p_cls < 0, 0, p_cls))
            else:
                p_clsb = ps[ns]["p_clsb"]
                expected_pvalues.append(np.where(p_clsb < 0, 0, p_clsb))

        return expected_pvalues