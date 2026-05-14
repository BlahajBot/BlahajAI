"""Tests for the one-shot /spark lane."""

from types import SimpleNamespace


def _import_cli():
    import hermes_cli.config as config_mod

    if not hasattr(config_mod, "save_env_value_secure"):
        config_mod.save_env_value_secure = lambda key, value: {
            "success": True,
            "stored_as": key,
            "validated": False,
        }

    import cli as cli_mod

    return cli_mod


def test_spark_command_registered():
    from hermes_cli.commands import resolve_command

    cmd = resolve_command("spark")

    assert cmd is not None
    assert cmd.name == "spark"
    assert "gpt-5.3-codex-spark" in cmd.description


def test_cli_spark_turn_route_is_one_shot_model_override():
    cli_mod = _import_cli()
    stub = SimpleNamespace(
        model="gpt-5.5",
        api_key="codex-token",
        base_url="https://chatgpt.com/backend-api/codex/responses",
        provider="openai-codex",
        api_mode="codex_responses",
        acp_command=None,
        acp_args=[],
        _credential_pool=None,
        service_tier="priority",
    )

    route = cli_mod.HermesCLI._resolve_turn_agent_config(
        stub,
        "tight edit please",
        spark_lane=True,
    )

    assert route["model"] == "gpt-5.3-codex-spark"
    assert route["runtime"]["provider"] == "openai-codex"
    assert route.get("request_overrides") is None
    assert route.get("spark_lane") is True
    # The session default remains untouched; /spark is one turn only.
    assert stub.model == "gpt-5.5"


def test_cli_spark_history_is_prompt_only_but_result_merges_back():
    cli_mod = _import_cli()
    prior = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "context"}]
    result_messages = [
        {"role": "user", "content": "spark prompt"},
        {"role": "assistant", "content": "spark answer"},
    ]

    assert cli_mod._history_for_spark_turn(prior) == []
    assert cli_mod._merge_spark_turn_history(prior, result_messages) == prior + result_messages
