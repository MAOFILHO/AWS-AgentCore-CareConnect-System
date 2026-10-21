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
        steps = [
            line.strip()
            for line in passages.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        text = "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))
        return DocumentProcessingResult(format="checklist", text=text)
