"""Offline behavior tests; the FUSE stand-in is limited to this fixture."""
import asyncio
import importlib
import logging
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def modules(monkeypatch):
    for name in ("remote_fuse.core", "remote_fuse.sharepoint"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    fuse = ModuleType("fuse")
    fuse.Stat = type("Stat", (), {})
    fuse.Fuse = type("Fuse", (), {})
    fuse.Direntry = lambda name: SimpleNamespace(name=name)
    fuse.feature_assert = lambda *args: None
    monkeypatch.setitem(sys.modules, "fuse", fuse)
    log = ModuleType("remote_fuse.logging")
    log.logger = logging.getLogger("remote-fuse-tests")
    monkeypatch.setitem(sys.modules, "remote_fuse.logging", log)
    core = importlib.import_module("remote_fuse.core")
    sharepoint = importlib.import_module("remote_fuse.sharepoint")
    yield core, sharepoint
    for name in ("remote_fuse.core", "remote_fuse.sharepoint"):
        sys.modules.pop(name, None)


@pytest.fixture
def fs(modules):
    core, _ = modules
    filesystem = core.FuseRemoteFilesystem.__new__(core.FuseRemoteFilesystem)
    filesystem.executor = SimpleNamespace(run=asyncio.run)
    filesystem.operations = SimpleNamespace(
        _fetch_file_content=AsyncMock(return_value=b"abcdef"),
        _upload_file_content=AsyncMock(),
    )
    return filesystem


def test_read_returns_requested_range(fs):
    assert fs.read("/file", 3, 2) == b"cde"


def test_write_preserves_surrounding_content(fs):
    assert fs.write("/file", b"XY", 2) == 2
    fs.operations._upload_file_content.assert_awaited_once_with("/file", b"abXYef")


def test_write_at_start_preserves_existing_tail(fs):
    assert fs.write("/file", b"XY", 0) == 2
    fs.operations._upload_file_content.assert_awaited_once_with("/file", b"XYcdef")


@pytest.mark.parametrize("length, expected", [(3, b"abc"), (0, b""), (8, b"abcdef\0\0")])
def test_truncate_with_sharepoint_backend_resizes_content(fs, modules, length, expected):
    _, sharepoint = modules
    operations = sharepoint.SharePointOperations.__new__(sharepoint.SharePointOperations)
    operations._fetch_file_content = AsyncMock(return_value=b"abcdef")
    operations._upload_file_content = AsyncMock()
    fs.operations = operations
    assert fs.truncate("/file", length) == 0
    operations._upload_file_content.assert_awaited_once_with("/file", expected)


def test_write_creates_missing_file(fs):
    from remote_fuse.exceptions import ItemDoesntExist
    fs.operations._fetch_file_content.side_effect = ItemDoesntExist
    assert fs.write("/new", b"new", 0) == 3
    fs.operations._upload_file_content.assert_awaited_once_with("/new", b"new")


def test_write_beyond_end_pads_with_zeros(fs):
    assert fs.write("/file", b"X", 8) == 1
    fs.operations._upload_file_content.assert_awaited_once_with("/file", b"abcdef\0\0X")


def test_failed_read_does_not_overwrite_existing_file(fs):
    import errno
    fs.operations._fetch_file_content.side_effect = RuntimeError("backend unavailable")
    assert fs.write("/file", b"X", 0) == -errno.EIO
    fs.operations._upload_file_content.assert_not_awaited()


def test_empty_sharepoint_file_has_zero_size(fs, modules):
    _, sharepoint = modules
    operations = sharepoint.SharePointOperations.__new__(sharepoint.SharePointOperations)
    operations._get_item_id = AsyncMock(return_value="file-id")
    item = SimpleNamespace(name="empty", folder=None, size=0, last_modified_date_time=None)
    operations.graph_client = MagicMock()
    operations.drive_id = "drive-id"
    builder = operations.graph_client.drives.by_drive_id.return_value.items.by_drive_item_id
    builder.return_value.get = AsyncMock(return_value=item)
    fs.operations = operations
    assert fs.getattr("/empty").st_size == 0


def test_sharepoint_attribute_errors_are_propagated(modules):
    _, sharepoint = modules
    operations = sharepoint.SharePointOperations.__new__(sharepoint.SharePointOperations)
    operations._get_item_id = AsyncMock(return_value="file-id")
    operations.graph_client = MagicMock()
    operations.drive_id = "drive-id"
    builder = operations.graph_client.drives.by_drive_id.return_value.items.by_drive_item_id
    error = sharepoint.APIError(response_status_code=403)
    builder.return_value.get = AsyncMock(side_effect=error)
    with pytest.raises(sharepoint.APIError):
        asyncio.run(operations._getattr("/file"))


def test_help_does_not_initialize_remote_storage(fs, modules, monkeypatch):
    core, _ = modules
    fs.operations.initialize = AsyncMock(side_effect=RuntimeError("must stay offline"))
    fs.fuse_args = SimpleNamespace(mount_expected=lambda: False)
    monkeypatch.setattr(core.Fuse, "main", lambda self: 0, raising=False)
    assert fs.main() == 0
    fs.operations.initialize.assert_not_awaited()


def test_backend_is_created_only_when_needed(modules, monkeypatch):
    core, _ = modules
    monkeypatch.setattr(
        core.Fuse, "__init__",
        lambda self, *args, **kwargs: setattr(self, "fuse_args", MagicMock()),
    )
    monkeypatch.setattr(core, "AsyncExecutor", MagicMock())
    backend = MagicMock()
    filesystem = core.FuseRemoteFilesystem(operations_class=backend)
    backend.assert_not_called()
    assert filesystem.operations is backend.return_value
    assert filesystem.operations is backend.return_value
    backend.assert_called_once_with()
