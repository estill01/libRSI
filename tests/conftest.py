"""Keep routine feedback short without changing the default full test suite."""

from pathlib import Path

import pytest

# Modules exceeding roughly 30 seconds in the 2026-09-06 baseline coverage run,
# plus adaptive scenarios, installed-wheel builds, and consumers of the cached
# Block 19 fixture (warm-cache baseline times hide their isolated setup cost).
# New modules remain fast by default; review --durations before adding here.
_SLOW_MODULES = frozenset(
    {
        "test_adaptive_loop.py",
        "test_block11_investigation_persistence.py",
        "test_block11_investigation_workflow.py",
        "test_block15_improvement_workflow.py",
        "test_block16_application_lifecycle.py",
        "test_block17_self_change_governance.py",
        "test_block17_validation_edges.py",
        "test_block18_facade.py",
        "test_block19_outcome_projections.py",
        "test_block19_projection_adversarial.py",
        "test_block19_projection_store.py",
        "test_block20_cli.py",
        "test_block20_external_controller.py",
        "test_block20_installed_cli.py",
        "test_block21_http.py",
        "test_block21_mcp.py",
        "test_block21_service.py",
        "test_block24_system_dogfoods.py",
        "test_block25_cross_domain_agnosticism.py",
        "test_block26_release_gate.py",
        "test_lightweight_durability.py",
        "test_lightweight_example.py",
        "test_lightweight_terminal.py",
    }
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if Path(item.path).name in _SLOW_MODULES:
            item.add_marker(pytest.mark.slow)
