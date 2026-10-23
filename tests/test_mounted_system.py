"""
This module tests sharepoint integration by mounting a test
site and working with it. It's not ideal test as it is a huge
side-effect, but it's effective in picking up bugs.

The site is shared and other people add content to it, so the test works
inside uniquely named folders and never asserts on the whole site.
"""
import shutil
import uuid
from pathlib import Path


def test_directory(fuse_sharepoint):
    mount_point = fuse_sharepoint
    print(f"FUSE filesystem mounted at {mount_point}")
    # Basic directory listing test
    directory = Path(mount_point)
    contents = {item.name for item in directory.iterdir()}
    assert {"General", "Shared Documents"} <= contents, "Expected the document libraries in the root"

    suffix = uuid.uuid4().hex[:8]
    general_dir = directory / "General" / f"remote-fuse-test-{suffix}"
    shared_docs_dir = directory / "Shared Documents" / f"remote-fuse-test-{suffix}"
    general_dir.mkdir()
    shared_docs_dir.mkdir()
    try:
        # File creation test
        empty_file = general_dir / "empty.txt"
        empty_file.touch()
        assert empty_file.exists(), "Failed to create empty file"

        # File writing test
        with open(empty_file, "w") as f:
            f.write("test")
        assert empty_file.read_text() == "test", "File content does not match expected value"

        # File rename test within same directory
        new_file_name = empty_file.parent / "new_file.txt"
        empty_file.rename(new_file_name)
        assert not empty_file.exists(), "Original file still exists after rename"
        assert new_file_name.exists(), "New file does not exist after rename"

        # File move test across directories
        different_parent = shared_docs_dir / "new_file.txt"
        new_file_name.rename(different_parent)
        assert not new_file_name.exists(), "Source file still exists after move"
        assert different_parent.exists(), "Destination file does not exist after move"

        # File deletion test
        different_parent.unlink()
        assert not different_parent.exists(), "File still exists after deletion"

        # Directory creation test
        empty_dir = general_dir / "empty_dir"
        empty_dir.mkdir()
        assert empty_dir.exists(), "Directory was not created"

        # Directory copy test
        copy_dir = general_dir / "copy_dir"
        shutil.copytree(empty_dir, copy_dir)
        assert copy_dir.exists(), "Directory copy does not exist"

        # Directory deletion tests
        empty_dir.rmdir()
        assert not empty_dir.exists(), "Directory still exists after removal"

        # Non-empty directory deletion test
        nonempty_file = copy_dir / "nonempty_file.txt"
        nonempty_file.write_text("Some content")

        shutil.rmtree(copy_dir)
        assert not copy_dir.exists(), "Copied directory still exists after removal"
    finally:
        shutil.rmtree(general_dir, ignore_errors=True)
        shutil.rmtree(shared_docs_dir, ignore_errors=True)
