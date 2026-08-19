from importlib.metadata import version

from voice_agent_eval_lab import __version__


def test_package_version_matches_release():
    assert __version__ == "0.3.0"


def test_distribution_metadata_matches_package_version():
    assert version("voice-agent-eval-lab") == __version__
