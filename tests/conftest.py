import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

topdir = Path(__file__).parent.parent


@pytest.fixture
def fuse_sharepoint():
    required = ("TENANT_ID", "CLIENT_ID", "CLIENT_SECRET", "SITE_ID")
    if any(not os.environ.get(name) for name in required):
        pytest.skip("Mounted integration tests require SharePoint credentials")
    if not shutil.which("fusermount") or not Path("/dev/fuse").exists():
        pytest.skip("Mounted integration tests require Linux FUSE")
    with TemporaryDirectory(dir=topdir) as tmpdir:
        st_dev = os.stat(tmpdir).st_dev
        proc = subprocess.Popen(
            [sys.executable, "-m", "commands.fuse_sharepoint", "-d", tmpdir],
            stdin=subprocess.DEVNULL,
        )
        mounted = False
        try:
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError(f"Filesystem exited before mounting: {proc.returncode}")
                if os.stat(tmpdir).st_dev != st_dev:
                    mounted = True
                    break
                time.sleep(.01)
            if not mounted:
                raise RuntimeError("Filesystem did not mount within 4s")
            yield Path(tmpdir)
        finally:
            if mounted:
                subprocess.run(["fusermount", "-u", "-q", "-z", tmpdir], check=True)
            try:
                if not mounted and proc.poll() is None:
                    proc.terminate()
                result = proc.wait(timeout=2)
                if mounted and result != 0:
                    raise RuntimeError(f"Filesystem exited with an error: {result}")
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise RuntimeError("Filesystem failed to exit within 2s after unmount")
