"""Ingest: reads approved documents only."""

from pathlib import Path


def load_approved(docs_root):
    """Return {document name: text} for docs_root/approved/*.md. No other folder is read."""
    return {p.name: p.read_text() for p in sorted((Path(docs_root) / "approved").glob("*.md"))}
