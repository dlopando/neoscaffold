"""Filesystem locations for the Social Studio database and media files."""

import os
import re

_EXTENSION_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVER_ROOT = os.path.abspath(os.path.join(_EXTENSION_DIR, "..", ".."))

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def server_root():
    return _SERVER_ROOT


def example_workflow_path():
    return os.path.join(_SERVER_ROOT, "example_workflows", "social_studio_dry_run.json")


def litegraph_path():
    return os.path.abspath(
        os.path.join(
            _SERVER_ROOT, "..", "neoscaffold", "public", "scripts", "litegraph.js"
        )
    )


def _configured_directory(server, attribute, env_name, default):
    configured = None
    if server is not None:
        configured = getattr(server, attribute, None)
    if not configured:
        configured = os.environ.get(env_name)
    if not configured:
        configured = default
    path = os.path.abspath(configured)
    os.makedirs(path, exist_ok=True)
    return path


def output_root(server=None):
    """Root directory for generated files. Honors --output-directory."""
    return _configured_directory(
        server,
        "output_directory",
        "NEOSCAFFOLD_OUTPUT_DIRECTORY",
        os.path.join(_SERVER_ROOT, "output"),
    )


def data_dir(server=None):
    path = os.path.join(output_root(server), "social_studio")
    os.makedirs(path, exist_ok=True)
    return path


def media_dir(server=None):
    path = os.path.join(data_dir(server), "media")
    os.makedirs(path, exist_ok=True)
    return path


def database_path(server=None):
    override = os.environ.get("SOCIAL_STUDIO_DATABASE")
    if override:
        parent = os.path.dirname(os.path.abspath(override))
        if parent:
            os.makedirs(parent, exist_ok=True)
        return os.path.abspath(override)
    return os.path.join(data_dir(server), "social_studio.db")


def safe_filename(value, default="file"):
    cleaned = _SAFE_NAME.sub("-", str(value or "")).strip(".-")
    return cleaned or default


def contained_file(directory, name):
    """Resolve a basename inside directory, rejecting path traversal."""
    if not name or os.path.basename(name) != name:
        return None
    directory = os.path.abspath(directory)
    path = os.path.abspath(os.path.join(directory, name))
    if os.path.commonpath([directory, path]) != directory:
        return None
    return path
