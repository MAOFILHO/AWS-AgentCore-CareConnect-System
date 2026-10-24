from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr


class ApiReply(BaseModel):
    """The API reply body: decision, reply and citations only."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["allow", "escalate", "block", "stop"]
    reply: StrictStr
    citations: list[StrictStr]
