import unittest

from careconnect.budget import BudgetExceeded, Budgets, BudgetTracker
from careconnect.fakes import FakeCostMeter


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def tracker(clock, meter=None, max_steps=8, max_seconds=30, max_cost_usd=0.5):
    budgets = Budgets(max_steps=max_steps, max_seconds=max_seconds, max_cost_usd=max_cost_usd)
    return BudgetTracker(budgets, meter or FakeCostMeter(), clock=clock)


class BudgetLimitTest(unittest.TestCase):
    def test_clock_past_max_seconds_raises(self):
        clock = FakeClock()
        t = tracker(clock)
        clock.now = 30.5
        with self.assertRaises(BudgetExceeded):
            t.step("x")

    def test_meter_total_past_max_cost_raises(self):
        t = tracker(FakeClock(), FakeCostMeter(cost_per_step=0.25))
        t.step("x")
        t.step("x")
        with self.assertRaises(BudgetExceeded):
            t.step("x")

    def test_exactly_at_every_limit_does_not_raise(self):
        clock = FakeClock()
        t = tracker(clock, FakeCostMeter(cost_per_step=0.25), max_steps=2)
        clock.now = 30
        t.step("x")
        t.step("x")
        self.assertEqual(t.steps, 2)
        self.assertEqual(t.cost_meter.total, 0.5)
