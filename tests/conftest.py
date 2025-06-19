import os
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

topdir = Path(__file__).parent.parent


@pytest.fixture
def fuse_sharepoint():
    with TemporaryDirectory(dir=topdir) as tmpdir:
        st_dev = os.stat(tmpdir).st_dev
        proc = subprocess.Popen([sys.executable, "-d", topdir / "src" / "commands" / "fuse_sharepoint.py", tmpdir], stdin=subprocess.DEVNULL)

        deadline = time.time() + 4
        while time.time() < deadline:
            new_st_dev = os.stat(tmpdir).st_dev
            if new_st_dev != st_dev:
                break
            time.sleep(.01)
        if new_st_dev == st_dev:
            proc.terminate()
            raise RuntimeError("Filesystem did not mount within 4s")


        yield Path(tmpdir)

        subprocess.call(["fusermount", "-u", "-q", "-z", tmpdir])

        deadline = time.time() + 2
        while time.time() < deadline:
            result = proc.poll()
            if result is not None:
                if result != 0:
                    raise RuntimeError("Filesystem exited with an error: {result}")
                return
            time.sleep(.01)

        proc.terminate()
        raise RuntimeError("Filesystem failed to exit within 2s after unmount")
