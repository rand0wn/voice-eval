from __future__ import annotations

from types import SimpleNamespace

import pytest

from voice_agent_eval_lab import adapters
from voice_agent_eval_lab.adapters import MockCascadeAdapter, VoicePipelineAdapter
from voice_agent_eval_lab.models import Scenario, TurnResult
from voice_agent_eval_lab.models import CompareRequest, RunRequest, RunReport, SuiteReport


class ExternalAdapter(VoicePipelineAdapter):
    name = "external"

    def execute(self, scenario: Scenario, audio_dir=None) -> list[TurnResult]:
        return []


def test_direct_registration_and_duplicate_handling(monkeypatch):
    monkeypatch.setattr(adapters, "_ADAPTERS", dict(adapters._ADAPTERS))
    adapters.register_adapter("external", ExternalAdapter)
    assert isinstance(adapters.get_adapter("EXTERNAL"), ExternalAdapter)
    with pytest.raises(ValueError, match="already registered"):
        adapters.register_adapter("external", ExternalAdapter)


def test_entry_point_registration(monkeypatch):
    monkeypatch.setattr(adapters, "_ADAPTERS", dict(adapters._ADAPTERS))
    monkeypatch.setattr(adapters, "_ENTRY_POINTS_LOADED", False)
    entry_point = SimpleNamespace(name="package-adapter", load=lambda: ExternalAdapter)
    monkeypatch.setattr(adapters.metadata, "entry_points", lambda **kwargs: [entry_point])
    assert "package-adapter" in adapters.available_adapters()
    assert isinstance(adapters.get_adapter("package-adapter"), ExternalAdapter)


def test_unknown_adapter_lists_choices(monkeypatch):
    monkeypatch.setattr(adapters, "_ENTRY_POINTS_LOADED", True)
    with pytest.raises(ValueError, match="Available adapters:.*cascade"):
        adapters.get_adapter("missing")


def test_factory_must_return_adapter(monkeypatch):
    monkeypatch.setattr(adapters, "_ADAPTERS", dict(adapters._ADAPTERS))
    adapters.register_adapter("bad", lambda: object())
    with pytest.raises(TypeError, match="expected VoicePipelineAdapter"):
        adapters.get_adapter("bad")


def test_builtin_behavior_is_unchanged():
    assert isinstance(adapters.get_adapter("cascade"), MockCascadeAdapter)


def test_models_accept_external_adapter_names():
    assert RunRequest(adapter="vendor-adapter").adapter == "vendor-adapter"
    assert CompareRequest(adapters=["vendor-adapter"]).adapters == ["vendor-adapter"]
    fields = RunReport.model_fields
    assert fields["adapter"].annotation is str
    assert SuiteReport.model_fields["adapter"].annotation is str
