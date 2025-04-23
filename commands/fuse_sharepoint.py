import fuse
from src.remote_fuse import FuseRemoteFilesystem
from src.sharepoint import SharePointOperations

def main():
    # Initialize filesystem
    fs = FuseRemoteFilesystem(
            operations_class=SharePointOperations,
            version="%prog " + fuse.__version__,
            dash_s_do='setsingle'
    )
    fs.usage = """
SharePoint FUSE filesystem

""" + fs.fusage

    fs.parser.add_option(
        "--site-id",
        metavar="site_id",
        help="Site identifier of the site that should be mounted (required if SITE_ID env var is unset)"
    )
    fs.parse(values=fs, errex=1)

    fs.main()

if __name__ == "__main__":
    main()
