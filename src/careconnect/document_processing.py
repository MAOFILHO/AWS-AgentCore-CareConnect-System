"""Document-Processing seam: turns sanitized passages into a checklist or plain text."""

import re
from typing import Literal

from pydantic import BaseModel


class DocumentProcessingResult(BaseModel):
    format: Literal["checklist", "text"]
    text: str


SEQUENCE_HEADING = r"^##.*\b(before|morning|arrive|arrival|after)\b"


class FakeDocumentProcessor:
    """Rule-based stand-in for the Document-Processing agent. Only reorders; adds nothing."""

    def process(self, passages):
        if len(re.findall(SEQUENCE_HEADING, passages, re.IGNORECASE | re.MULTILINE)) < 2:
            return DocumentProcessingResult(format="text", text=passages)
        lines = []
        n = 0
        for line in passages.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                n = 0
                lines.append(line.lstrip("#").strip())
            else:
                n += 1
                lines.append(f"{n}. {line}")
        return DocumentProcessingResult(format="checklist", text="\n".join(lines))
