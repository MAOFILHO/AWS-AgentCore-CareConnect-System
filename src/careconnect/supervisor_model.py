"""Supervisor model name, read from model.json (no default: a missing file raises FileNotFoundError)."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, constr

CONFIG_PATH = Path(__file__).with_name("model.json")


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supervisor_model: constr(min_length=1)


def load_supervisor_model(path=None):
    return ModelConfig.model_validate_json(Path(path or CONFIG_PATH).read_text()).supervisor_model
