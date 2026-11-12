"""The larger panel is registered before selection and retains paired resampling."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import extend_native_confirmation as confirmation  # noqa: E402


def test_registration_is_fixed_and_rejects_late_outcome_driven_expansion(tmp_path):
    source = tmp_path / "early"
    source.mkdir()
    (source / "runs").mkdir()
    (source / "protocol.json").write_text(json.dumps({"seed_bases": {"test": 839000}}))
    confirmation.register(source)
    plan = json.loads((source / "confirmation-amendment.json").read_text())
    assert plan["test_workloads"] == 512 and plan["native_runs_completed_at_registration"] == 0
    with pytest.raises(ValueError, match="already exists"):
        confirmation.register(source)
    late = tmp_path / "late"
    late.mkdir()
    (late / "frozen-improver.json").write_text("{}")
    with pytest.raises(ValueError, match="before meta"):
        confirmation.register(late)


def test_expanded_crossed_bootstrap_preserves_constant_paired_effect():
    a = np.tile((np.arange(512) % 4) * 0.02, (32, 1))
    result = confirmation.contrast({"a": a, "b": a + 0.03}, "a", "b")
    assert result["independent_workloads"] == 512
    assert result["mean_effect"] == pytest.approx(0.03)
    assert result["bootstrap_95_percentile"] == pytest.approx([0.03, 0.03])
