import pytest

from crossfraud.data.synthetic import SynthConfig, generate


@pytest.fixture(scope="session")
def data():
    raw, truth = generate(SynthConfig())
    return raw, truth
