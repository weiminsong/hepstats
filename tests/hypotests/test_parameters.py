#!/usr/bin/python
import pytest
import numpy as np
import zfit

from hepstats.hypotests.parameters import POI, POIarray

mean = zfit.Parameter("mu", 1.2, 0.1, 2)


def test_pois():

    p0 = POI(mean, 0)
    p1 = POI(mean, 1.)
    values = np.linspace(0., 1.0, 10)
    pn = POIarray(mean, values)

    for cls in [POI, POIarray]:
        with pytest.raises(ValueError):
            cls("mean", 0)
        with pytest.raises(TypeError):
            cls(mean)

    with pytest.raises(TypeError):
        POI(mean, values)
    with pytest.raises(TypeError):
        POIarray(mean, 0)

    print(p0)

    assert p0.value == 0
    assert p0.name == mean.name
    assert p0 != p1

    assert all(pn.values == values)
    assert pn.name == mean.name
    assert len(pn) == len(values)
    iter(pn)

    assert pn[0] == p0
    assert pn[1] != p0
    assert pn[-1] == p1

    # test hash
    {p0: "p0", p1: "p1", pn: "pn"}
