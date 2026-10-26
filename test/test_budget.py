import unittest

from careconnect.budget import BudgetExceeded, Budgets, BudgetTracker, StepPriceMeter, load_budgets
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


class StepPriceMeterTest(unittest.TestCase):
    def test_charges_the_configured_price_per_step(self):
        meter = StepPriceMeter({"Verification Agent": 0.01, "Combine safe results": 0.0})
        meter.charge("Verification Agent")
        meter.charge("Combine safe results")
        meter.charge("Verification Agent")
        self.assertAlmostEqual(meter.total, 0.02)

    def test_unpriced_step_raises(self):
        with self.assertRaises(KeyError):
            StepPriceMeter({}).charge("Verification Agent")

    def test_default_config_prices_model_calls(self):
        self.assertGreater(load_budgets().step_cost_usd["Verification Agent"], 0)


class DefaultPriceTableTest(unittest.TestCase):
    def test_worst_case_run_trips_the_cap_when_every_agent_runs(self):
        b = load_budgets()
        t = BudgetTracker(b, StepPriceMeter(b.step_cost_usd))
        with self.assertRaises(BudgetExceeded):
            for name in b.step_cost_usd:
                t.step(name)
        self.assertLessEqual(t.steps, b.max_steps)
        self.assertGreater(t.cost_meter.total, b.max_cost_usd)

    def test_one_agent_answer_stays_well_under_the_cap(self):
        b = load_budgets()
        meter = StepPriceMeter(b.step_cost_usd)
        for name in ("Safety gate (input check)", "Create execution plan", "Retrieval Agent",
                     "Combine safe results", "Verification Agent"):
            meter.charge(name)
        self.assertLess(meter.total, b.max_cost_usd / 2)
