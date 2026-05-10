from amodb.apps.platform.command_registry import catalog, get_definition


def test_command_catalog_is_allowlisted():
    names = {item["command_name"] for item in catalog()}
    assert "RUN_PLATFORM_HEALTH_PROBE" in names
    assert "RUN_THROUGHPUT_PROBE" in names
    assert "rm -rf /" not in names


def test_unsupported_commands_are_explicitly_marked():
    definition = get_definition("INFRA_FAILOVER_DATABASE")
    assert definition is not None
    assert definition.supported is False
    assert definition.risk_level == "CRITICAL"
