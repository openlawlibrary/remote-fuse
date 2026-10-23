# FUSE File System for accessing remote servers

A FUSE file system for mounting remote file servers as local directories.
Currently, we support Microsoft SharePoint sites.

## Installation

```bash
pip install remote-fuse
```

## Configuration

The following environment variables need to be set:

- `TENANT_ID`: Azure AD tenant ID
- `CLIENT_ID`: Azure AD client/application ID
- `CLIENT_SECRET`: Azure AD client secret
- `SITE_ID`: SharePoint site ID

## Running

```bash
# Mount remote cloud storage
remote-fuse <mounting-point>
# Optionally, add `--site-id <site-id>` to override SITE_ID.

# Unmount when finished
fusermount -uqz <mount-point>
```

## Development

```bash
# Install dependencies
python3.10 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# For development/testing
pip install -e ".[test]"
```

## Requirements

- Python 3.10 or newer
- Linux with FUSE 2. On Ubuntu, install `fuse`, `libfuse-dev`, and `pkg-config`
  before installing this package. Native mounting on macOS is not supported.

## Usage

```bash
# Mount SharePoint site as local directory
python src/commands/fuse_sharepoint.py <mount-point> [--site-id optional]

# Unmount SharePoint site when finished
fusermount -uqz <mount-point>

# Run tests
pytest
```

Offline regression tests run without credentials. SharePoint integration tests
need all four environment variables; mounted tests also need `/dev/fuse` and
`fusermount`. Tests skip when these requirements are missing. Integration tests
create and remove uniquely named folders on the configured site.

The `fuse-sharepoint` command remains available as an alias for `remote-fuse`.

With uv, use `uv sync --locked --all-extras` and `uv run --locked pytest`.
The `.python-version` file selects Python 3.10.

## Overview of the project

* `src/remote_fuse/core.py`: Implements Fuse interface and by invoking API calls to remote service
* `src/remote_fuse/sharepoint.py`: Implements the interface to present SharePoint as a local filesystem
* `src/commands/fuse_sharepoint.py`: Mounts SharePoint site as local directory

## python-fuse documentation

Currently, python-fuse only supports Linux.
There is no easy way to stop the process once started, it doesn't react to signals,
however, it will stop if you unmount it.
https://github.com/libfuse/python-fuse/blob/master/README.new_fusepy_api.rst
