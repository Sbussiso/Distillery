"""Shared fixtures. Point the datasets dir at a temp folder before the app
is imported, and give each test its own store root."""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("DISTILLERY_DATASETS_DIR", tempfile.mkdtemp(prefix="distillery_tests_"))

import pytest  # noqa: E402

from distillery.store import store  # noqa: E402


@pytest.fixture(autouse=True)
def datasets_root(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setattr(store, "root", root)
    return root
