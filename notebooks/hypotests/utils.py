import numpy as np
import matplotlib.pyplot as plt
import zfit

def pltdist(data, bins, bounds):
    y, bin_edges = np.histogram(data, bins=bins, range=bounds)
    bin_centers = 0.5*(bin_edges[1:]+bin_edges[:-1])
    yerr = np.sqrt(y)
    width = 0.05
    plt.errorbar(bin_centers, y, yerr=yerr, fmt=".", color="royalblue")
    
    
def plotfitresult(model, bounds, nbins, data):
    x = np.linspace(*bounds, num=1000)
    pdf = zfit.run(model.pdf(x, norm_range=bounds)* model.get_yield())
    _ = plt.plot(x, ((bounds[1] - bounds[0])/nbins)*(pdf), "-r", label="fit result")