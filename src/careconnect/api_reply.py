from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr


class ApiReply(BaseModel):
    """The API reply body: decision, reply, citations and the staged flag only."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["allow", "escalate", "block", "stop"]
    reply: StrictStr
    citations: list[StrictStr]
    staged: StrictBool = False
