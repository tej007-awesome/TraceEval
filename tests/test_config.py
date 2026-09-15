import importlib
import os
import sys

from pydantic import SecretStr

import traceeval.core.config as config


def test_import_config_does_not_modify_os_environ(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    if "traceeval.core.config" in sys.modules:
        importlib.reload(sys.modules["traceeval.core.config"])
    else:
        import traceeval.core.config  # noqa: F401

    assert "OPENAI_API_KEY" not in os.environ
    assert "OPENAI_BASE_URL" not in os.environ


def test_get_judge_client_llm_api_key_set(monkeypatch):
    monkeypatch.setattr(config.settings, "llm_api_key", SecretStr("test-llm-key"))
    monkeypatch.setattr(config.settings, "llm_base_url", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = config.get_judge_client()
    assert client.api_key == "test-llm-key"
    assert str(client.base_url) == "https://api.openai.com/v1/"


def test_get_judge_client_only_openai_api_key_set(monkeypatch):
    monkeypatch.setattr(config.settings, "llm_api_key", None)
    monkeypatch.setattr(config.settings, "llm_base_url", None)
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")

    client = config.get_judge_client()
    assert client.api_key == "env-openai-key"
    assert str(client.base_url) == "https://api.openai.com/v1/"


def test_get_judge_client_only_llm_base_url_set(monkeypatch):
    monkeypatch.setattr(config.settings, "llm_api_key", None)
    monkeypatch.setattr(config.settings, "llm_base_url", "http://localhost:11434/v1/")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = config.get_judge_client()
    assert client.api_key == "not-needed"
    assert str(client.base_url) == "http://localhost:11434/v1/"
