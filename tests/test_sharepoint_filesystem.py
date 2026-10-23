"""
This module tests sharepoint API by invoking it through
FuseRemoteFilesystem API. This does not mount the filesystem.
We use pathlib like API to test integration with SharePoint.

The site is shared and other people add content to it, so every test works
inside its own uniquely named folder and never asserts on the whole site.
"""
import errno
import os
import stat
import uuid

import pytest

pytest.importorskip("fuse", reason="SharePoint integration requires the native FUSE binding")

from remote_fuse.core import FuseRemoteFilesystem
from remote_fuse.sharepoint import SharePointOperations

@pytest.fixture
def fs():
    """Test filesystem operations against the real SharePoint site"""
    # Check for required environment variables
    required_vars = ['TENANT_ID', 'CLIENT_ID', 'CLIENT_SECRET', 'SITE_ID']
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        pytest.skip(f"SharePoint credentials are missing: {', '.join(missing)}")

    fs = FuseRemoteFilesystem(operations_class=SharePointOperations)
    # initialization is done as part of main method, so we have to do it by hand here
    fs.executor.run(fs.operations.initialize())
    return fs


def is_directory(attrs):
    return bool(attrs.st_mode & stat.S_IFDIR)


def names(entries):
    return [e.name for e in entries if e.name not in [".", ".."]]


def remove_tree(fs: FuseRemoteFilesystem, path: str):
    entries = fs.readdir(path, 0)
    if isinstance(entries, int):
        return
    for name in names(entries):
        child = f"{path}/{name}"
        attrs = fs.getattr(child)
        if not isinstance(attrs, int) and is_directory(attrs):
            remove_tree(fs, child)
        else:
            fs.unlink(child)
    fs.rmdir(path)


def make_workspace(fs: FuseRemoteFilesystem, library: str):
    path = f"/{library}/remote-fuse-test-{uuid.uuid4().hex[:8]}"
    assert fs.mkdir(path) is None
    return path


@pytest.fixture
def shared_docs(fs: FuseRemoteFilesystem):
    path = make_workspace(fs, "Shared Documents")
    yield path
    remove_tree(fs, path)


@pytest.fixture
def general(fs: FuseRemoteFilesystem):
    path = make_workspace(fs, "General")
    yield path
    remove_tree(fs, path)


def test_readdir_sharepoint(fs: FuseRemoteFilesystem, shared_docs: str):
    root_items = names(fs.readdir("/", 0))
    assert "Shared Documents" in root_items
    assert "General" in root_items
    assert is_directory(fs.getattr("/Shared Documents"))

    subdir_path = f"{shared_docs}/test_folder"
    assert fs.mkdir(subdir_path) is None
    assert fs.write(f"{subdir_path}/test1.txt", b"first", 0) == 5
    assert fs.write(f"{subdir_path}/test2.txt", b"second", 0) == 6

    assert names(fs.readdir(shared_docs, 0)) == ["test_folder"]
    assert is_directory(fs.getattr(subdir_path))

    subsubdir_items = names(fs.readdir(subdir_path, 0))
    assert sorted(subsubdir_items) == ["test1.txt", "test2.txt"]
    for subitem in subsubdir_items:
        assert not is_directory(fs.getattr(f"{subdir_path}/{subitem}"))


def test_readdir_empty_folder_sharepoint(fs: FuseRemoteFilesystem, general: str):
    assert names(fs.readdir(general, 0)) == []


def test_read_file_sharepoint(fs: FuseRemoteFilesystem, shared_docs: str):
    file_path = f"{shared_docs}/test3.txt"
    expected = b"Another test file" * 50
    fs.write(file_path, expected, 0)

    file_attrs = fs.getattr(file_path)
    assert file_attrs.st_size == len(expected)
    assert fs.read(file_path, file_attrs.st_size, 0) == expected


def test_create_empty_directory_sharepoint(fs: FuseRemoteFilesystem, shared_docs: str):
    sharepoint_path = f"{shared_docs}/empty_dir"

    fs.mkdir(sharepoint_path)
    dir_contents = fs.readdir(sharepoint_path, 0)
    entry_names = [d.name for d in dir_contents]

    assert entry_names == [".", ".."]


def test_delete_empty_directory_sharepoint(fs: FuseRemoteFilesystem, shared_docs: str):
    sharepoint_path = f"{shared_docs}/empty_dir"
    fs.mkdir(sharepoint_path)

    fs.rmdir(sharepoint_path)

    # Assert there is not directory
    ret = fs.readdir(sharepoint_path, 0)
    assert ret == -errno.ENOENT


def test_create_file_sharepoint(fs: FuseRemoteFilesystem, shared_docs: str):
    sharepoint_path = f"{shared_docs}/test_file.txt"

    fs.write(sharepoint_path, b"custom content", 0)
    file_attrs = fs.getattr(sharepoint_path)
    file_contents = fs.read(sharepoint_path, file_attrs.st_size, 0)

    assert file_contents == b"custom content"


def test_delete_file_sharepoint(fs: FuseRemoteFilesystem, shared_docs: str):
    sharepoint_path = f"{shared_docs}/test_file.txt"
    fs.write(sharepoint_path, b"custom content", 0)

    fs.unlink(sharepoint_path)

    file_attrs = fs.getattr(sharepoint_path)
    assert file_attrs == -errno.ENOENT


def test_rename_file_sharepoint(fs: FuseRemoteFilesystem, shared_docs: str):
    old_path = f"{shared_docs}/test_file.txt"
    new_path = f"{shared_docs}/new_test_file.txt"

    # create file
    fs.write(old_path, b"custom content", 0)

    # rename it
    fs.rename(old_path, new_path)

    # read renamed version
    file_attrs = fs.getattr(new_path)
    content = fs.read(new_path, file_attrs.st_size, 0)
    assert content == b"custom content"

    # expect fail when reading read old version
    file_attrs = fs.getattr(old_path)
    assert file_attrs == -errno.ENOENT


def test_rename_file_different_parent_sharepoint(
    fs: FuseRemoteFilesystem, shared_docs: str, general: str
):
    old_path = f"{shared_docs}/new_test_file.txt"
    new_path = f"{general}/test_file.txt"

    # create file
    fs.write(old_path, b"custom content", 0)

    # rename it
    fs.rename(old_path, new_path)

    # read renamed version
    file_attrs = fs.getattr(new_path)
    content = fs.read(new_path, file_attrs.st_size, 0)
    assert content == b"custom content"
    # remove it
    fs.unlink(new_path)

    # expect fail when reading old version
    file_attrs = fs.getattr(old_path)
    assert file_attrs == -errno.ENOENT
