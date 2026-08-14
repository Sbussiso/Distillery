"""Distillery — local LLM distillation app."""
from __future__ import annotations


def main() -> None:
    # Re-export so the `distillery` console script works.
    from . import __main__

    __main__.main()


__all__ = ["main"]