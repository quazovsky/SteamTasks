"""Backoff and supervisor-policy tests — no Discord required."""

from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worthlesstask.core.backoff import BackoffPolicy
from worthlesstask.core.errors import is_fatal_close


class TestBackoff(unittest.TestCase):
    def test_growth_is_exponential(self):
        policy = BackoffPolicy(base_delay=1.0, factor=2.0, max_delay=60.0, jitter=0.0)
        self.assertEqual([policy.delay_for(n) for n in (1, 2, 3, 4)], [1.0, 2.0, 4.0, 8.0])

    def test_capped_at_max_delay(self):
        policy = BackoffPolicy(base_delay=1.0, factor=2.0, max_delay=10.0, jitter=0.0)
        self.assertEqual(policy.delay_for(50), 10.0)

    def test_jitter_stays_within_bounds(self):
        policy = BackoffPolicy(base_delay=4.0, factor=1.0, max_delay=4.0, jitter=0.5)
        rng = random.Random(0)
        for _ in range(200):
            delay = policy.delay_for(1, rng)
            self.assertGreaterEqual(delay, 2.0)
            self.assertLessEqual(delay, 6.0)

    def test_should_retry_honours_max_attempts(self):
        policy = BackoffPolicy(max_attempts=3)
        self.assertTrue(policy.should_retry(1))
        self.assertTrue(policy.should_retry(2))
        self.assertFalse(policy.should_retry(3))

    def test_should_retry_is_unbounded_by_default(self):
        self.assertTrue(BackoffPolicy().should_retry(10_000))

    def test_invalid_parameters_are_rejected(self):
        for kwargs in (
            {"base_delay": 0},
            {"factor": 0.5},
            {"max_delay": 0.5, "base_delay": 1.0},
            {"jitter": 1.0},
            {"max_attempts": 0},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                BackoffPolicy(**kwargs)

    def test_attempt_is_one_based(self):
        with self.assertRaises(ValueError):
            BackoffPolicy().delay_for(0)

    def test_round_trip_dict(self):
        policy = BackoffPolicy(base_delay=2.0, factor=3.0, max_delay=30.0, jitter=0.1, max_attempts=7)
        self.assertEqual(BackoffPolicy.from_dict(policy.to_dict()), policy)


class TestCloseCodePolicy(unittest.TestCase):
    def test_invalid_client_id_is_fatal(self):
        self.assertTrue(is_fatal_close(4000))

    def test_rate_limit_is_retryable(self):
        self.assertFalse(is_fatal_close(4002))

    def test_unknown_code_is_retryable(self):
        self.assertFalse(is_fatal_close(None))
        self.assertFalse(is_fatal_close(9999))


if __name__ == "__main__":
    unittest.main(verbosity=2)
