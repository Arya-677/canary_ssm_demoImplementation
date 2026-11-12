import numpy as np
import pytest

from canary_ssm.simulate import SimConfig, simulate
from canary_ssm.preprocess import fit_nuisance


@pytest.fixture(scope="session")
def nuis():
    rs = [simulate(SimConfig(), s, False)[0] for s in range(30)]
    return fit_nuisance(rs)


@pytest.fixture(scope="session")
def pair():
    c = SimConfig()
    return simulate(c, 777, True), simulate(c, 777, False)
