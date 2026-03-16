from pathlib import Path
import tempfile
import unittest

from cclf_liquidity_model import ScenarioConfig, load_scenarios, run_scenario, run_scenarios, summarize


class LiquidityModelTests(unittest.TestCase):
    def test_run_scenario_returns_expected_quarter_count(self) -> None:
        rows = run_scenario(ScenarioConfig(name="Test", quarters=4))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["Quarter"], 1)
        self.assertEqual(rows[-1]["Quarter"], 4)

    def test_summarize_detects_shortfall(self) -> None:
        rows = run_scenario(
            ScenarioConfig(
                name="Shortfall",
                quarters=2,
                tender_rate=0.25,
                annual_default_rate=0.1,
                unfunded_draw_rate=0.5,
                starting_cash=0.0,
                min_cash_buffer=0.0,
            )
        )
        summary = summarize(rows)
        self.assertEqual(summary["first_liquidity_shortfall_quarter"], 1)

    def test_config_validation_rejects_invalid_rates(self) -> None:
        with self.assertRaises(ValueError):
            ScenarioConfig(name="Bad", tender_rate=1.1).validate()

    def test_load_scenarios_reads_wrapped_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "scenarios.json"
            path.write_text('{"scenarios": [{"name": "Base"}]}', encoding="utf-8")
            scenarios = load_scenarios(path)
            self.assertEqual(len(scenarios), 1)
            self.assertEqual(scenarios[0].name, "Base")

    def test_run_scenarios_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            run_scenarios([ScenarioConfig(name="Smoke", quarters=1)], output_dir=out_dir, print_tables=False)
            self.assertTrue((out_dir / "smoke_projection.csv").exists())
            self.assertTrue((out_dir / "scenario_summary.csv").exists())
            self.assertTrue((out_dir / "effective_scenarios.json").exists())


if __name__ == "__main__":
    unittest.main()
