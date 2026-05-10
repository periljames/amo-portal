from amodb.apps.platform.command_registry import get_definition


def test_no_arbitrary_shell_command_registered():
    assert get_definition("shell") is None
    assert get_definition("RUN_ARBITRARY_COMMAND") is None
