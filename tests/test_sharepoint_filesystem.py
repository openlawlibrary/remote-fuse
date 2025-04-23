"""
This module tests sharepoint API by invoking it through
FuseRemoteFilesystem API. This does not mount the filesystem.
We use pathlib like API to test integration with SharePoint.
"""
import errno
import os
import sys
import pytest

from remote_fuse import FuseRemoteFilesystem
from sharepoint import SharePointOperations

@pytest.fixture
def fs():
    """Test filesystem operations against the real SharePoint site"""
    # Check for required environment variables
    required_vars = ['TENANT_ID', 'CLIENT_ID', 'CLIENT_SECRET', 'SITE_ID']
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        print(f"Error: Missing required environment variables: {', '.join(missing)}")
        print("Please set them before running this test.")
        sys.exit(1)
    
    fs = FuseRemoteFilesystem(operations_class=SharePointOperations)
    # initialization is done as part of main method, so we have to do it by hand here
    fs.executor.run(fs.operations.initialize())
    return fs


def test_readdir_sharepoint(fs: FuseRemoteFilesystem):
    # Test listing root directory
    root_contents = fs.readdir("/", 0)
    assert len(root_contents) == 4
    items = [i for i in root_contents if i.name not in [".", ".."]]

    shared_docs = next(i.name for i in items if i.name == "Shared Documents")
    # Get attributes
    attrs = fs.getattr(f"/{shared_docs}")
    file_type = "Directory" if attrs.st_mode & 0o40000 else "File"
    assert file_type == "Directory"

    # If it's a directory, try to list its contents
    subdir_path = f"/{shared_docs}"
    subdir_contents = fs.readdir(subdir_path, 0)
    subdir_items = [i.name for i in subdir_contents if i.name not in [".", ".."]]

    assert len(subdir_items) == 2
    subsubdir_path = f"{subdir_path}/test_folder"
    subdir_attrs = fs.getattr(subsubdir_path)
    subfile_type = "Directory" if subdir_attrs.st_mode & 0o40000 else "File"
    assert subfile_type == "Directory"

    subsubdir_contents = fs.readdir(subsubdir_path, 0)
    subsubdir_items = [i.name for i in subsubdir_contents if i.name not in [".", ".."]]
    assert len(subsubdir_items) == 2
    for subitem in subsubdir_items:
        print(f"    - {subitem}")
        subsubattrs = fs.getattr(f"{subsubdir_path}/{subitem}")
        file_type = "Directory" if subsubattrs.st_mode & 0o40000 else "File"
        assert file_type == "File"

    general = next(i.name for i in items if i.name == "General")
    general_contents = fs.readdir(general, 0)
    general_items = [i for i in general_contents if i.name not in [".", ".."]]
    assert len(general_items) == 0


def test_read_file_sharepoint(fs: FuseRemoteFilesystem):
    # Test listing root directory
    file_path = "/Shared Documents/test_folder/test3.txt"
    file_attrs = fs.getattr(file_path)
    root_contents = fs.read(file_path, file_attrs.st_size, 0)

    assert root_contents == b"Another test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test fileAnother test file"


def test_create_empty_directory_sharepoint(fs: FuseRemoteFilesystem):
    # Test listing root directory
    sharepoint_path = "/empty_dir"

    fs.mkdir(sharepoint_path)
    dir_contents = fs.readdir(sharepoint_path, 0)
    entry_names = [d.name for d in dir_contents]

    assert entry_names == [".", ".."]


def test_delete_empty_directory_sharepoint(fs: FuseRemoteFilesystem):
    # Test listing root directory
    sharepoint_path = "/empty_dir"

    fs.rmdir(sharepoint_path)

    # Assert there is not directory
    ret = fs.readdir(sharepoint_path, 0)
    assert ret == -errno.ENOENT


def test_create_file_sharepoint(fs: FuseRemoteFilesystem):
    # Test listing root directory
    sharepoint_path = "/Shared Documents/test_file.txt"

    fs.write(sharepoint_path, b"custom content", 0)
    file_attrs = fs.getattr(sharepoint_path)
    file_contents = fs.read(sharepoint_path, file_attrs.st_size, 0)

    assert file_contents == b"custom content"
    

def test_delete_file_sharepoint(fs: FuseRemoteFilesystem):
    # Test listing root directory
    sharepoint_path = "/Shared Documents/test_file.txt"

    fs.unlink(sharepoint_path)

    file_attrs = fs.getattr(sharepoint_path)
    assert file_attrs == -errno.ENOENT


def test_rename_file_sharepoint(fs: FuseRemoteFilesystem):
    old_path = "/Shared Documents/test_file.txt"
    new_path = "/Shared Documents/new_test_file.txt"

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


def test_rename_file_different_parent_sharepoint(fs: FuseRemoteFilesystem):
    old_path = "/Shared Documents/new_test_file.txt"
    new_path = "/General/test_file.txt"

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
