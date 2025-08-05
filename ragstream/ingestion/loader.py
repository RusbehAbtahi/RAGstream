"""
DocumentLoader
==============
Responsible for discovering and loading raw files from *data/doc_raw*.
"""
from pathlib import Path
from typing import List

class DocumentLoader:
    """Scans the raw-document directory and yields file paths."""
    def __init__(self, root: Path) -> None:
        self.root = root

    def load_documents(self) -> List[str]:
        """Return a list of file paths (as strings); real parsing is deferred."""
        return []
