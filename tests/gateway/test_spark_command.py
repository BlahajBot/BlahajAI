"""Gateway tests for the one-shot /spark lane."""


def test_gateway_spark_turn_route_is_one_shot_model_override():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner._service_tier = "priority"
    runtime = {
        "api_key": "codex-token",
        "base_url": "https://chatgpt.com/backend-api/codex/responses",
        "provider": "openai-codex",
        "api_mode": "codex_responses",
        "command": None,
        "args": [],
        "credential_pool": None,
    }

    route = GatewayRunner._resolve_turn_agent_config(
        runner,
        "tight edit please",
        "gpt-5.5",
        runtime,
        spark_lane=True,
    )

    assert route["model"] == "gpt-5.3-codex-spark"
    assert route["runtime"]["provider"] == "openai-codex"
    assert route.get("request_overrides") == {}
    assert route.get("spark_lane") is True
