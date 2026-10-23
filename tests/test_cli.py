"""Exercise installed commands with the native FUSE binding, without credentials."""
import os
import subprocess
from importlib.metadata import version

import pytest

pytest.importorskip("fuse", reason="CLI smoke tests require the native FUSE binding")


@pytest.mark.parametrize("command", ["remote-fuse", "fuse-sharepoint"])
@pytest.mark.parametrize("option", ["--help", "--version"])
def test_cli_information_without_credentials(command, option):
    env = os.environ.copy()
    for name in ("TENANT_ID", "CLIENT_ID", "CLIENT_SECRET", "SITE_ID"):
        env.pop(name, None)
    result = subprocess.run(
        [command, option], env=env, capture_output=True, text=True, timeout=10,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert ("--site-id" if option == "--help" else version("remote-fuse")) in output
