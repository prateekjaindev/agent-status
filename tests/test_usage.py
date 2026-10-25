import unittest

from agent_status.procs import agent_key
from agent_status.usage import PRICES, claude_cost, context_window, finish_rows, new_row, price_for, tps


class Pricing(unittest.TestCase):
    def test_longest_prefix(self):
        self.assertEqual(price_for("claude-opus-5-5[1m]"), PRICES["claude-opus-5-5"])
        self.assertEqual(price_for("claude-opus-5"), PRICES["claude-opus-5"])
        self.assertIsNone(price_for("gpt-6"))

    def test_cost_includes_cache_writes_by_ttl(self):
        u = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000,
             "cache_creation_input_tokens": 2_000_000, "cache_creation": {"ephemeral_1h_input_tokens": 1_000_000}}
        # $4 in + $20 out + $0.20 cache read + 1M x 5-min write at 1.25x + 1M x 1-hour write at 2x
        self.assertAlmostEqual(claude_cost("claude-opus-5-5", u), 4 + 20 + 0.2 + 5 + 8)
        self.assertIsNone(claude_cost("unknown", u))

    def test_context_window(self):
        self.assertEqual(context_window("claude-opus-5-5"), 1_000_000)
        self.assertEqual(context_window("claude-sonnet-4-6"), 1_000_000)
        self.assertEqual(context_window("claude-haiku-4-5"), 200_000)

    def test_tps_guards(self):
        self.assertEqual(tps(100, 2), 50)
        self.assertIsNone(tps(5, 2))      # too few tokens to mean anything
        self.assertIsNone(tps(100, 1000))  # someone walked away mid-turn

    def test_rows(self):
        r = new_row("x", "m")
        r.update(output=10, input=5, tps_out=10, tps_sec=2)
        unpriced = new_row("y", "n")
        unpriced["priced"] = False
        rows = finish_rows([r, unpriced])
        self.assertEqual((rows[0]["tps"], rows[0]["total"]), (5, 15))
        self.assertIsNone(rows[1]["cost"])


class ProcessMatching(unittest.TestCase):
    def test_names_and_npm_packages(self):
        self.assertEqual(agent_key("claude", None), "claude")
        self.assertEqual(agent_key("node", ["node", "/usr/lib/node_modules/@github/copilot/index.js"]), "copilot")
        self.assertEqual(agent_key("node", ["node", "/usr/bin/cursor-agent"]), "cursor")
        self.assertIsNone(agent_key("node", ["node", "server.js"]))
        self.assertIsNone(agent_key("bash", None))


if __name__ == "__main__":
    unittest.main()
