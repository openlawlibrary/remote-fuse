import os
import stat
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.exceptions import ItemDoesntExist
from src.logging import logger
from src.remote_fuse import RemoteOperations, RemoteStat

from fuse import Direntry

from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient
from msgraph.generated.models.drive_item import DriveItem
from msgraph.generated.models.file import File
from msgraph.generated.models.folder import Folder
from msgraph.generated.models.item_reference import ItemReference

class SharePointOperations(RemoteOperations):
    def __init__(self):
        self.tenant_id = os.environ.get("TENANT_ID")
        self.client_id = os.environ.get("CLIENT_ID")
        self.client_secret = os.environ.get("CLIENT_SECRET")
        self.site_id = os.environ.get("SITE_ID")
        self.drive_id = None

        if not all([self.tenant_id, self.client_id, self.client_secret]):
            raise ValueError("Missing required environment variables: TENANT_ID, CLIENT_ID, CLIENT_SECRET")

        # Initialize Graph client
        scopes = ["https://graph.microsoft.com/.default"]
        credential = ClientSecretCredential(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret=self.client_secret
        )
        self.graph_client = GraphServiceClient(credential, scopes)

        # Store root path
        self.path_to_id_map = {"/": "root"}

    async def initialize(self):
        """Initialize site and drive IDs"""
        self.drive_id = await self._get_drive_id()

    async def _get_drive_id(self) -> str:
        """Get default document library drive ID"""
        try:
            drive = await self.graph_client.sites.by_site_id(self.site_id).drive.get()
            return drive.id
        except Exception as e:
            logger.error(f"Failed to get drive ID: {e}")
            raise

    async def _get_directory_contents(self, path: str) -> List[str]:
        """Get directory contents as a list of names directly from SharePoint"""
        # Special handling for macOS hidden files
        if os.path.basename(path).startswith("._"):
            logger.debug(f"Ignoring macOS metadata path: {path}")
            return []
        try:
            # Special case for root directory
            if path == "/":
                logger.debug("Listing root directory contents")
                try:
                    items = await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id("root").children.get()
                    file_names = [Direntry(item.name) for item in items.value]
                    logger.debug(f"Found {len(file_names)} items in root: {file_names}")

                    # Cache the item IDs for child paths to speed up future lookups
                    for item in items.value:
                        child_path = os.path.join(path, item.name)
                        if child_path.startswith("//"):  # Fix double slashes
                            child_path = child_path[1:]
                        self.path_to_id_map[child_path] = item.id
                        logger.debug(f"Cached item ID for {child_path}: {item.id}")

                    return file_names
                except Exception as root_error:
                    logger.error(f"Error listing root directory: {root_error}", exc_info=True)
                    return []

            # For other directories, get the ID for the path
            item_id = await self._get_item_id(path)
            logger.debug(f"Got item_id: {item_id} for path: {path}")
            if not item_id:
                logger.error(f"Could not find path: {path}")
                raise ItemDoesntExist(f"Could not find path: {path}")

            # Map paths to item IDs to speed up future lookups
            self.path_to_id_map[path] = item_id

            logger.debug(f"Requesting children for drive_id: {self.drive_id}, item_id: {item_id}")
            try:
                items = await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id(item_id).children.get()

                # Log what we found
                file_names = [Direntry(item.name) for item in items.value]
                logger.debug(f"Found {len(file_names)} items in {path}: {file_names}")

                # Cache the item IDs for child paths to speed up future lookups
                for item in items.value:
                    child_path = os.path.join(path, item.name)
                    if child_path.startswith("//"):  # Fix double slashes
                        child_path = child_path[1:]
                    self.path_to_id_map[child_path] = item.id
                    logger.debug(f"Cached item ID for {child_path}: {item.id}")

                # Return just the item names
                return file_names
            except Exception as e:
                logger.error(f"Error fetching directory children for {path}: {e}", exc_info=True)
                return []
        except ItemDoesntExist as e:
            logger.debug(f"Item doesn't exist: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to get directory contents for {path}: {e}")
            return []

    async def _getattr(self, path: str) -> RemoteStat:
        """Get file attributes asynchronously"""
        if os.path.basename(path).startswith("._"):
            logger.debug(f"Ignoring macOS metadata path: {path}")
            raise ItemDoesntExist("Ignore macOS metadata paths")
        # Special case for root directory
        if path == "/":
            return RemoteStat()

        # For any other path, get item details from SharePoint
        try:
            item_id = await self._get_item_id(path)
            if not item_id:
                raise ItemDoesntExist(f"Item ID not found for path {path}")

            # Get item details directly from SharePoint
            item = await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id(item_id).get()

            # Properly determine if an item is a folder or file
            # In Graph API, items have either a folder property or a file property
            is_dir = hasattr(item, "folder") and getattr(item, "folder", None) is not None
            logger.debug(f"Item {item.name}: folder property: {getattr(item, 'folder', None)}, file property: {getattr(item, 'file', None)}, is_dir: {is_dir}")
            mode = 0o755 | stat.S_IFDIR if is_dir else 0o644 | stat.S_IFREG
            size = item.size if item.size and not is_dir else 4096
            last_modified = item.last_modified_date_time.timestamp() if item.last_modified_date_time else datetime.now().timestamp()

            st = RemoteStat()
            st.st_mode = mode
            st.st_nlink = 2 if is_dir else 1
            st.st_size = size
            st.st_ctime = last_modified
            st.st_mtime = last_modified
            st.st_atime = last_modified
            return st
        except ItemDoesntExist:
            logger.error(f"Could not find item for path {path}")
            raise
        except Exception as e:
            logger.error(f"Failed to get attributes for {path}: {e}")
            raise

    async def _get_item_id(self, path: str) -> Optional[str]:
        """Get item ID for a path"""
        if os.path.basename(path).startswith("._"):
            logger.debug(f"Ignoring macOS metadata path: {path}")
            return None
        logger.debug(f"_get_item_id: original path: {path}")
        # Check if the path is already in our cache
        if path in self.path_to_id_map:
            logger.debug(f"Found cached item ID for {path}: {self.path_to_id_map[path]}")
            return self.path_to_id_map[path]

        # Check if it's the root path
        if path == "/":
            return "root"

        # Normalize path - remove any double slashes and trailing slashes
        path = os.path.normpath(path)
        logger.debug(f"_get_item_id: nromalized path: {path}")
        if path == ".":
            path = "/"

        # For any other path, we need to look up the ID by traversing the path
        try:
            # Find the parent path and item name
            parent_path = os.path.dirname(path)
            if parent_path == "":
                parent_path = "/"
            item_name = os.path.basename(path)

            logger.debug(f"Looking up item ID for path: {path}, parent: {parent_path}, name: {item_name}")

            # Get parent directory contents
            try:
                if parent_path == "/":
                    logger.debug(f"Getting root children for drive: {self.drive_id}")
                    items = await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id("root").children.get()
                else:
                    parent_id = await self._get_item_id(parent_path)
                    if not parent_id:
                        logger.error(f"Parent ID not found for {parent_path}")
                        raise ItemDoesntExist(f"Parent ID not found for {parent_path}")

                    logger.debug(f"Getting children for parent_id: {parent_id}")
                    items = await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id(parent_id).children.get()

                logger.debug(f"Retrieved {len(items.value)} items from SharePoint")
            except ItemDoesntExist:
                raise
            except Exception as e:
                logger.error(f"Error fetching directory contents for {path}: {e}", exc_info=True)
                return None

            # Find matching item
            for item in items.value:
                # Compare in a case-insensitive way to handle SharePoint's behavior
                if item.name.lower() == item_name.lower():
                    # Cache the result for future lookups
                    self.path_to_id_map[path] = item.id
                    logger.debug(f"Found and cached item ID for {path}: {item.id}")
                    return item.id

            # Item not found
            logger.warning(f"Item not found for path: {path}")
            return None
        except ItemDoesntExist as e:
            logger.debug(f"Item doesn't exist: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to get item ID for {path}: {e}")
            return None

    async def _create_file(self, path: str) -> int:
        """Create a new empty file in SharePoint and return its ID"""
        if os.path.basename(path).startswith("._"):
            logger.debug(f"Ignoring macOS metadata path: {path}")
            return 0
        try:
            parent_path = str(Path(path).parent)

            # Get parent ID
            parent_id = await self._get_item_id(parent_path)
            if parent_id is None:
                parent_id = "root"

            # Create file
            response = await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id(parent_id).children.post(
                DriveItem(
                    name = Path(path).name,
                    file = File(),
                    additional_data = {
                        "@microsoft_graph_conflict_behavior" : "rename",
                    }
                )
            )

            # Extract the new file ID
            new_file_id = response.id
            self.path_to_id_map[path] = new_file_id
            return new_file_id
        except Exception as e:
            logger.error(f"Failed to create file {path}: {e}")
            raise

    async def _delete_file(self, path: str) -> None:
        """Delete a file from SharePoint"""
        if os.path.basename(path).startswith("._"):
            logger.debug(f"Ignoring macOS metadata path: {path}")
            return None
        try:
            # Get item ID
            item_id = await self._get_item_id(path)
            if not item_id:
                raise ItemDoesntExist(f"Item ID not found for path {path}")

            # Delete the file
            await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id(item_id).delete()

            # remove file from cache
            self.path_to_id_map.pop(path)
            logger.info(f"Deleted file {path}")
        except Exception as e:
            logger.error(f"Failed to delete file {path}: {e}")
            raise

    async def _fetch_file_content(self, path: str) -> bytes:
        """Fetch file content from SharePoint"""
        if os.path.basename(path).startswith("._"):
            logger.debug(f"Ignoring macOS metadata path: {path}")
            return b""
        try:
            # Get item ID
            item_id = await self._get_item_id(path)
            if not item_id:
                raise ItemDoesntExist(f"Item ID not found for path {path}")

            # Get content
            response = await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id(item_id).content.get()
            return response
        except Exception as e:
            logger.error(f"Failed to fetch content for {path}: {e}")
            raise

    async def _upload_file_content(self, path: str, content: bytes) -> None:
        """Upload file content to SharePoint"""
        if os.path.basename(path).startswith("._"):
            logger.debug(f"Ignoring macOS metadata path: {path}")
            return None
        try:
            # Get item ID
            item_id = await self._get_item_id(path)
            if not item_id:
                # File doesn't exist yet, create it
                item_id = await self._create_file(path)

            # Upload content
            await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id(item_id).content.put(
                content
            )
        except Exception as e:
            logger.error(f"Failed to upload content for {path}: {e}")
            raise

    async def _create_folder(self, path: str) -> None:
        """Create a new folder in SharePoint"""
        if os.path.basename(path).startswith("._"):
            logger.debug(f"Ignoring macOS metadata path: {path}")
            return None
        try:
            parent_path = str(Path(path).parent)
            parent_id = await self._get_item_id(parent_path)
            # Create folder
            await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id(parent_id).children.post(
                DriveItem(
                    name = Path(path).name,
                    folder = Folder(),
                    additional_data = {
                        "@microsoft_graph_conflict_behavior" : "rename",
                    }
                )
            )
                
            return None
        except Exception as e:
            logger.error(f"Failed to create folder {path}: {e}")
            raise

    async def _delete_folder(self, path: str) -> None:
        """Delete a folder from SharePoint"""
        if os.path.basename(path).startswith("._"):
            logger.debug(f"Ignoring macOS metadata path: {path}")
            return None
        try:
            # Get item ID
            item_id = await self._get_item_id(path)
            if not item_id:
                raise ItemDoesntExist(f"Item ID not found for path {path}")
                    
            # Delete folder
            await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id(item_id).delete()
                    
            self.path_to_id_map.pop(path)
            logger.info(f"Deleted folder {path}")
        except Exception as e:
            logger.error(f"Failed to delete folder {path}: {e}")
            raise

    async def _rename_file(self, old_path: str, new_path: str) -> None:
        """Rename a file in SharePoint"""
        if os.path.basename(old_path).startswith("._"):
            logger.debug(f"Ignoring macOS metadata path: {old_path}")
            return None
        try:
            # Get item ID
            item_id = await self._get_item_id(old_path)
            if not item_id:
                raise ItemDoesntExist(f"Item ID not found for path {old_path}")

            _old_path = Path(old_path)
            _new_path = Path(new_path)
            old_parent = _old_path.parent
            new_parent = _new_path.parent
            if old_parent == new_parent:
                # Rename the file
                await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id(item_id).patch(
                    DriveItem(
                        name = _new_path.name,
                    )
                )
            else:
                # Move the file to the new parent
                new_parent_id = await self._get_item_id(str(new_parent))
                await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id(item_id).patch(
                    DriveItem(
                        name = _new_path.name,
                        parent_reference = ItemReference(
                            id = new_parent_id,
                        ),
                        additional_data = {
                            "@microsoft_graph_conflict_behavior" : "rename",
                        }
                    )
                )

            self.path_to_id_map.pop(old_path)
            self.path_to_id_map[new_path] = item_id
            logger.info(f"Renamed file {old_path} to {new_path}")
        except Exception as e:
            logger.error(f"Failed to rename file {old_path} to {new_path}: {e}")
            raise

