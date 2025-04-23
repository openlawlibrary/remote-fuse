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
# Optionally, you can add `--site-id <site-id` as an argument to the command.

# Unomunt when finished
fusermount -uqz <mount-point>
```

## Development

```bash
# Install dependencies
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# For development/testing
pip install -e ".[test]"
```

## Requirements

- FUSE implementation (libfuse2 on Ubuntu, macFUSE on macOS)

## Usage

```bash
# Mount SharePoint site as local directory
python commands/fuse_sharepoint.py <mount-point>

# Unomunt SharePoint site when finished
fusermount -uqz <mount-point>

# Run tests
pytest
```

## Overview of the project

* `src/remote_fuse.py`: Implements Fuse interface and by invoking API calls to remote service
* `src/sharepoint.py`: Implements the interface to present SharePoint as a local filesystem
* `commands/fuse_sharepoint.py`: Mounts SharePoint site as local directory

## python-fuse documentation

Currently, python-fuse only supports Linux.
There is no easy way to stop the process once started, it doesn't react to signals,
however, it will stop if you unmount it.
https://github.com/libfuse/python-fuse/blob/master/README.new_fusepy_api.rst
