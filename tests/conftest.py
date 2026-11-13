from pathlib import Path

import pytest

from meridian_iam import generate_hr_data

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("data")
    truth = generate_hr_data.main(out)
    return out, truth
