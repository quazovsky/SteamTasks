"""Resolver scoring and transport discovery tests — no network, no Discord."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worthlesstask.presence.resolver import (
    Candidate,
    DetectableIndex,
    normalize,
    score_entry,
    search_offline,
)
from worthlesstask.rpc.transport import candidate_paths

FIXTURE = [
    {
        "id": "357607133254254632",
        "name": "Dead by Daylight",
        "aliases": ["DbD"],
        "icon_hash": "abc",
        "hook": True,
        "executables": [
            {"name": "deadbydaylight-win64-shipping.exe", "os": "win32"},
            {"name": "deadbydaylight.exe", "os": "win32"},
        ],
    },
    {
        "id": "363409179668512788",
        "name": "The Forest",
        "aliases": [],
        "icon_hash": "def",
        "hook": True,
        "executables": [{"name": "theforest.exe", "os": "win32"}],
    },
    {
        "id": "1384276457596911676",
        "name": "PEAK",
        "aliases": [],
        "icon_hash": "ghi",
        "hook": True,
        "executables": [{"name": "peak/peak.exe", "os": "win32"}],
    },
]


class TestNormalize(unittest.TestCase):
    def test_strips_punctuation_and_case(self):
        self.assertEqual(normalize("Dead by Daylight"), "deadbydaylight")
        self.assertEqual(normalize("The Forest!"), "theforest")

    def test_handles_non_strings(self):
        self.assertEqual(normalize(123), "123")


class TestScoring(unittest.TestCase):
    def test_exact_name_wins(self):
        score, matched = score_entry(FIXTURE[0], "Dead by Daylight")
        self.assertEqual(score, 100)
        self.assertEqual(matched, "name-exact")

    def test_case_and_punctuation_insensitive(self):
        self.assertEqual(score_entry(FIXTURE[0], "dead  by   DAYLIGHT")[0], 100)

    def test_alias_match(self):
        score, matched = score_entry(FIXTURE[0], "dbd")
        self.assertEqual(score, 95)
        self.assertTrue(matched.startswith("alias"))

    def test_executable_match(self):
        score, matched = score_entry(FIXTURE[2], "peak.exe")
        self.assertEqual(score, 75)
        self.assertTrue(matched.startswith("executable"))

    def test_prefix_and_substring(self):
        self.assertEqual(score_entry(FIXTURE[1], "The")[1], "name-prefix")
        self.assertEqual(score_entry(FIXTURE[1], "forest")[1], "name-substring")

    def test_no_match(self):
        self.assertEqual(score_entry(FIXTURE[1], "Halo"), (0, ""))

    def test_empty_query_matches_nothing(self):
        self.assertEqual(score_entry(FIXTURE[1], "   "), (0, ""))


class TestIndex(unittest.TestCase):
    def _index(self) -> DetectableIndex:
        index = DetectableIndex(cache_path=Path("unused.json"), fetch=lambda _url: b"[]")
        index._entries = list(FIXTURE)
        return index

    def test_search_ranks_exact_first(self):
        results = self._index().search("The Forest")
        self.assertEqual(results[0].id, "363409179668512788")
        self.assertEqual(results[0].name, "The Forest")

    def test_search_limit(self):
        self.assertEqual(len(self._index().search("e", limit=2)), 2)

    def test_best_respects_min_score(self):
        self.assertIsNotNone(self._index().best("The Forest"))
        self.assertIsNone(self._index().best("Halo Infinite"))

    def test_by_id(self):
        candidate = self._index().by_id("1384276457596911676")
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.name, "PEAK")
        self.assertIsNone(self._index().by_id("000"))

    def test_candidate_icon_url(self):
        candidate = Candidate(id="1", name="G", score=100, matched_on="name-exact", icon_hash="h")
        self.assertEqual(candidate.icon_url, "https://cdn.discordapp.com/app-icons/1/h.png")

    def test_offline_helper(self):
        results = search_offline(FIXTURE, "peak")
        self.assertEqual(results[0].name, "PEAK")


class TestTransportDiscovery(unittest.TestCase):
    def test_candidates_are_non_empty(self):
        self.assertTrue(candidate_paths())

    def test_windows_candidates_are_pipe_paths(self):
        import os

        if os.name != "nt":
            self.skipTest("windows-only assertion")
        paths = candidate_paths()
        self.assertTrue(all(p.startswith("\\\\") for p in paths))
        self.assertIn(r"\\.\pipe\discord-ipc-0", paths)
        self.assertEqual(len(paths), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
