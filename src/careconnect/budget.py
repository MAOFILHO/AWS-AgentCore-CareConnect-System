"""Supervisor budgets: steps, seconds and cost, read from config.json."""

import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

CONFIG_PATH = Path(__file__).with_name("config.json")
BUDGET_MESSAGE = "This request is taking too long, so I stopped. Please try again or call us."


class Budgets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_steps: PositiveInt
    max_seconds: float = Field(gt=0, allow_inf_nan=False)
    max_cost_usd: float = Field(gt=0, allow_inf_nan=False)


def load_budgets(path=CONFIG_PATH):
    return Budgets.model_validate_json(Path(path).read_text())


class BudgetExceeded(Exception):
    pass


class BudgetTracker:
    def __init__(self, budgets, cost_meter, clock=None):
        self.budgets = budgets
        self.cost_meter = cost_meter
        self.clock = clock or time.monotonic
        self.start = self.clock()
        self.steps = 0

    def step(self, name):
        """Count one step, charge the meter, and raise if any limit is passed."""
        self.steps += 1
        self.cost_meter.charge(name)
        if (
            self.steps > self.budgets.max_steps
            or self.clock() - self.start > self.budgets.max_seconds
            or self.cost_meter.total > self.budgets.max_cost_usd
        ):
            raise BudgetExceeded(name)
