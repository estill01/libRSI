"""A supplemental transfer check cannot silently change the primary comparison."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import check_native_development_transfer as transfer  # noqa: E402


def test_transfer_interval_preserves_known_effect_on_shared_workloads():
    a = np.tile((np.arange(512) % 4) * 0.03, (24, 1))
    result = transfer.contrast(a, a - 0.02, 2026111215)
    assert result["mean_effect"] == pytest.approx(-0.02)
    assert result["bootstrap_97_5_percentile"] == pytest.approx([-0.02, -0.02])


def test_transfer_registration_refuses_completed_final_systems(tmp_path):
    (tmp_path / "frozen-final-systems.json").write_text("[]")
    with pytest.raises(ValueError, match="before final systems"):
        transfer.register(tmp_path)
