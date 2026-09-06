from __future__ import annotations

import pytest

from examples.embedded_improvement import run_example


def test_embedded_example_measures_rejects_then_resumes_without_repeating(tmp_path) -> None:
    report = run_example(tmp_path)
    assert report["status"] == "completed"
    assert report["disposition"] == "improved"
    assert report["completed_cycles"] == [1, 2]
    assert report["candidate_experiments"] == 2
    assert report["resumed_after_cycle"] == 1
    assert report["baseline_error"] == 4
    assert report["candidate_errors"] == [3, 1]
    assert report["application_performed"] is False
    with pytest.raises(FileExistsError, match="fresh --data-dir"):
        run_example(tmp_path)
