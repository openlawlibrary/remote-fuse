import errno
import os
import stat
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

import fuse
from fuse import Direntry, Fuse

from src.exceptions import ItemDoesntExist
from src.logging import logger
from src.utils import AsyncExecutor

fuse.fuse_python_api = (0, 2)
fuse.feature_assert('stateful_files', 'has_init')


class RemoteOperations(Protocol):
    """Protocol for operations required by FuseRemoteFilesystem.

    Implement methods from this protocol to support new remote filesystem.
    """
    async def initialize(self) -> None:
        """Initialize remote file system connection."""
        ...

    async def _get_directory_contents(self, path: str) -> List[str]:
        """Get list of items in a directory."""
        ...

    async def _getattr(self, path: str, fh: Optional[int] = None) -> Dict[str, Any]:
        """Get file/directory attributes."""
        ...

    async def _create_file(self, path: str) -> int:
        """Create a new empty file."""
        ...

    async def _delete_file(self, path: str) -> None:
        """Delete a file."""
        ...

    async def _fetch_file_content(self, path: str) -> bytes:
        """Fetch content of a file."""
        ...

    async def _upload_file_content(self, path: str, content: bytes) -> None:
        """Upload content to a file."""
        ...
        
    async def _truncate_file(self, path: str, length: int) -> None:
        """Truncate a file to specified length."""
        ...

    async def _create_folder(self, path: str) -> None:
        """Create a new folder."""
        ...

    async def _delete_folder(self, path: str) -> None:
        """Delete a folder."""
        ...

    async def _rename_file(self, old_path: str, new_path: str) -> None:
        """Rename or move a file."""
        ...


class RemoteStat(fuse.Stat):
    def __init__(self):
        self.st_mode = stat.S_IFDIR | 0o755
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 2
        self.st_uid = os.getgid()
        self.st_gid = os.getgid()
        self.st_size = 4096
        self.st_atime = datetime.now().timestamp()
        self.st_mtime = datetime.now().timestamp()
        self.st_ctime = datetime.now().timestamp()


class FuseRemoteFilesystem(Fuse):
    """FUSE implementation that delegates to a remote file system.
    
    This class provides a bridge between FUSE operations and a remote file system
    defined by the RemoteOperations protocol.
    """
    
    def __init__(self, operations_class, *args, **kwargs):
        """Initialize the filesystem.
        
        Args:
            operations_class: Class that implements RemoteOperations
            *args: Arguments to pass to Fuse.__init__
            **kwargs: Keyword arguments to pass to Fuse.__init__
        """
        Fuse.__init__(self, *args, **kwargs)

        self.operations = operations_class()
        self.executor = AsyncExecutor()

        self.multithreaded = True
        self.fuse_args.setmod('foreground')

        # Add these FUSE mount options to prevent deadlocks
        self.fuse_args.add("direct_io")        # Bypass kernel caching
        self.fuse_args.add("entry_timeout=0")  # Disable directory entry caching
        self.fuse_args.add("attr_timeout=0")   # Disable attribute caching
        self.fuse_args.add("negative_timeout=0") # Disable negative response caching
        self.fuse_args.add("intr")             # Allow requests to be interrupted
        self.fuse_args.add("big_writes")       # Enable larger writes 

    def statfs(self):
        """Return filesystem statistics"""
        stats = fuse.StatVfs()
        stats.f_bsize = 4096  # Preferred block size
        stats.f_frsize = 4096  # Fundamental block size
        stats.f_blocks = 1000000  # Total blocks
        stats.f_bfree = 900000   # Free blocks
        stats.f_bavail = 900000  # Free blocks available to non-superuser
        stats.f_files = 1000000  # Total inodes
        stats.f_ffree = 900000   # Free inodes
        stats.f_favail = 900000  # Free inodes for non-superuser
        stats.f_fsid = 0         # Filesystem ID
        stats.f_flag = 0         # Mount flags
        stats.f_namemax = 255    # Maximum filename length
        return stats

    def readdir(self, path: str, offset: int) -> List[Direntry] | int:
        """List contents of a directory."""
        dirents = [Direntry("."), Direntry("..")]
        try:
            logger.debug(f"Reading directory contents for {path}")
            # Run async operation in the current thread
            dirents_from_remote = self.executor.run(self.operations._get_directory_contents(path))
            dirents.extend(dirents_from_remote)
            logger.debug(f"Directory {path} contains: {dirents}")
            return dirents
        except ItemDoesntExist as e:
            logger.error(f"Item doesn't exist: {e}")
            return -errno.ENOENT
        except Exception as e:
            logger.error(f"Failed to read directory {path}: {e}")
            return -errno.EIO

    def getattr(self, path: str) -> RemoteStat | int:
        """Get attributes of a file or directory."""
        logger.debug(f"getattr called for path: {path}")
        try:
            stat_obj = self.executor.run(self.operations._getattr(path))
            logger.debug(f"Got stat object for {path}: {vars(stat_obj)}")
            return stat_obj
        except ItemDoesntExist as e:
            logger.debug(f"Item doesn't exist for path {path}, raising ENOENT; error: {e}")
            return -errno.ENOENT
        except Exception as e:
            logger.error(f"Unexpected error in getattr for {path}: {e}")
            return -errno.EIO

    def create(self, path: str, flags: int, mode: int = 0o666):
        """Create a new file."""
        logger.debug(f"Creating file: {path} with flags: {flags} and mode: {mode}")
        try:
            # Create empty file in remote storage
            file_id = self.executor.run(self.operations._create_file(path))
            logger.info(f"Created new file {path} with ID {file_id}")
            return (file_id, False)
        except Exception as e:
            logger.error(f"Create failed: {e}")
            return -errno.EIO

    def unlink(self, path: str):
        """Delete a file."""
        logger.debug(f"Deleting file: {path}")
        try:
            # Delete file directly from remote storage
            self.executor.run(self.operations._delete_file(path))
            return 0
        except ItemDoesntExist as e:
            logger.error(f"Item doesn't exist: {e}")
            return -errno.ENOENT
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return -errno.EIO

    def mkdir(self, path: str, mode: int = 0o755) -> None | int:
        """Create a directory."""
        try:
            logger.debug(f"Creating directory: {path}")
            self.executor.run(self.operations._create_folder(path))
            return None
        except Exception as e:
            logger.error(f"Create directory failed: {e}")
            return -errno.EIO

    def rmdir(self, path: str) -> None | int:
        """Delete a directory."""
        try:
            logger.debug(f"Deleting directory: {path}")
            self.executor.run(self.operations._delete_folder(path))
            return None
        except ItemDoesntExist as e:
            logger.error(f"Item doesn't exist: {e}")
            return -errno.ENOENT
        except Exception as e:
            logger.error(f"Delete directory failed: {e}")
            return -errno.EIO

    def rename(self, old_path: str, new_path: str) -> int:
        """Rename or move a file or directory."""
        try:
            logger.debug(f"Renaming file: {old_path} to {new_path}")
            self.executor.run(self.operations._rename_file(old_path, new_path))
            return 0
        except ItemDoesntExist as e:
            logger.error(f"Item doesn't exist: {e}")
            return -errno.ENOENT
        except Exception as e:
            logger.error(f"Rename failed: {e}")
            return -errno.EIO

    def chmod(self, path: str, mode: int) -> None:
        return None

    def chown(self, path: str, uid: int, gid: int) -> None:
        return None

    def read(self, path: str, size: int, offset: int) -> bytes | int:
        """Read data from a file."""
        logger.debug(f"Reading file: {path} of size {size} offset: {offset}")
        try:
            # Fetch content directly from remote storage
            content = self.executor.run(self.operations._fetch_file_content(path))

            # Return requested portion
            return content[offset:offset + size]
        except ItemDoesntExist as e:
            logger.error(f"Item doesn't exist: {e}")
            return -errno.ENOENT
        except Exception as e:
            logger.error(f"Read failed: {e}")
            return -errno.EIO

    def write(self, path: str, data: bytes, offset: int, fh=None) -> int:
        """Write data to a file."""
        logger.debug(f"Writing to file: {path}, {len(data)} bytes at offset: {offset}")
        try:
            # Need to read current content first if offset > 0 or not writing to the end
            current_content = b""
            if offset > 0:
                try:
                    current_content = self.executor.run(self.operations._fetch_file_content(path))
                except ItemDoesntExist:
                    # File might not exist yet
                    pass
                except Exception as e:
                    logger.error(f"Failed to read current content: {e}")
                    return -errno.EIO

            # If offset is beyond current size, pad with zeros
            if offset > len(current_content):
                current_content = current_content + b"\0" * (offset - len(current_content))

            # Create new content by replacing a portion of current content with new data
            if offset + len(data) > len(current_content):
                # Append or partial overwrite
                new_content = current_content[:offset] + data
            else:
                # Insert in the middle
                new_content = current_content[:offset] + data + current_content[offset + len(data):]

            # Upload to remote storage
            self.executor.run(self.operations._upload_file_content(path, new_content))

            # Return number of bytes written
            return len(data)
        except Exception as e:
            logger.error(f"Write failed: {e}")
            return -errno.EIO

    def access(self, path: str, mode):
        """Check file access permissions."""
        try:
            if mode == os.F_OK:
                # Just check if file exists
                self.executor.run(self.operations._getattr(path))
            return 0
        except ItemDoesntExist:
            return -errno.ENOENT
        except Exception:
            return -errno.EIO

    def open(self, path: str, flags, *args):
        """Handle file open, including creation if O_CREAT is set."""
        logger.debug(f"open called with path: {path}, flags: {flags}")
        try:
            # Check if this is a create operation
            if flags & os.O_CREAT:
                self.executor.run(self.operations._create_file(path))
                return 0
            # For regular open, just verify the file exists
            self.executor.run(self.operations._getattr(path))
            return 0
        except ItemDoesntExist:
            return -errno.ENOENT
        except Exception as e:
            logger.error(f"Open failed: {e}")
            return -errno.EIO

    def truncate(self, path: str, length: int) -> int:
        """Truncate a file to a specified length."""
        logger.debug(f"Truncating file: {path} to length: {length}")
        try:
            # Implement proper truncate operation
            if hasattr(self.operations, '_truncate_file'):
                # Use dedicated truncate if available
                self.executor.run(self.operations._truncate_file(path, length))
            else:
                # Fallback implementation
                current_content = self.executor.run(self.operations._fetch_file_content(path))
                
                # Adjust content length
                if length < len(current_content):
                    # Truncate to shorter length
                    new_content = current_content[:length]
                else:
                    # Extend with zeros
                    new_content = current_content + b"\0" * (length - len(current_content))
                    
                # Upload modified content
                self.executor.run(self.operations._upload_file_content(path, new_content))
                
            return 0
        except ItemDoesntExist as e:
            logger.error(f"Item doesn't exist: {e}")
            return -errno.ENOENT
        except Exception as e:
            logger.error(f"Truncate failed: {e}")
            return -errno.EIO

    def utimens(self, path: str, ts_acc: float, ts_mod: float) -> None | int:
        return 0

    def main(self, *args, **kwargs):
        # site_id is available only after parsing if it is not in the environment vars
        site_id = getattr(self, "site_id", None)
        if site_id is not None:
            self.operations.site_id = site_id
        # Run initialization asynchronously since now we should have all variables
        self.executor.run(self.operations.initialize())

        return Fuse.main(self, *args, **kwargs)

