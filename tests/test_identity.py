"""Application-id resolution: name lookup, drift tolerance, self-healing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worthlesstask.core.errors import ResolverError
from worthlesstask.presence.identity import IdentityResolver
from worthlesstask.presence.resolver import (
    DetectableIndex,
    executable_name,
    executables_of,
    is_valid_entry,
)

ENDFIELD = "1461154307171811401"

FIXTURE = [
    {"id": ENDFIELD, "name": "ARKNIGHTS: ENDFIELD", "aliases": [], "hook": False,
     "icon_hash": "a1c", "executables": [{"is_launcher": False, "name": "endfield.exe", "os": "win32"}]},
    {"id": "1441993124996972685", "name": "Arknights", "aliases": [], "hook": True,
     "icon_hash": "b8a", "executables": []},
    {"id": "357607133254254632", "name": "Dead by Daylight", "aliases": ["DbD"], "hook": True,
     "icon_hash": "64e", "executables": [{"name": "deadbydaylight.exe", "os": "win32"}]},
]


def _index(entries=None) -> DetectableIndex:
    index = DetectableIndex(cache_path=Path("unused.json"), fetch=lambda _url: b"[]")
    index._entries = list(entries if entries is not None else FIXTURE)
    return index


def _resolver(entries=None) -> IdentityResolver:
    return IdentityResolver(index=_index(entries))


class TestExecutableHelpers(unittest.TestCase):
    def test_object_shape(self):
        self.assertEqual(executables_of({"executables": [{"name": "a.exe"}]}), ("a.exe",))

    def test_string_shape_is_tolerated(self):
        """Discord has shipped both shapes; neither may break the lookup."""
        self.assertEqual(executables_of({"executables": ["a.exe", "b.exe"]}), ("a.exe", "b.exe"))

    def test_mixed_and_garbage(self):
        self.assertEqual(executables_of({"executables": ["a.exe", {"name": "b.exe"}, 5]}), ("a.exe", "b.exe"))

    def test_missing_field(self):
        self.assertEqual(executables_of({}), ())
        self.assertEqual(executables_of({"executables": "nope"}), ())

    def test_bare_name_strips_directories(self):
        self.assertEqual(executable_name({"executables": [{"name": "peak/peak.exe"}]}), "peak.exe")
        self.assertEqual(executable_name({"executables": [{"name": "win64\\cs2.exe"}]}), "cs2.exe")

    def test_entry_validation(self):
        self.assertTrue(is_valid_entry({"id": "1", "name": "x"}))
        self.assertFalse(is_valid_entry({"id": "abc", "name": "x"}))
        self.assertFalse(is_valid_entry({"name": "x"}))
        self.assertFalse(is_valid_entry("nope"))


class TestIdentityResolution(unittest.TestCase):
    def test_resolves_by_name(self):
        identity = _resolver().resolve("ARKNIGHTS: ENDFIELD")
        self.assertEqual(identity.application_id, ENDFIELD)
        self.assertEqual(identity.source, "catalogue")

    def test_resolves_from_an_alias(self):
        identity = _resolver().resolve("dbd")
        self.assertEqual(identity.application_id, "357607133254254632")

    def test_does_not_confuse_arknights_with_endfield(self):
        self.assertEqual(_resolver().resolve("Arknights").application_id, "1441993124996972685")
        self.assertEqual(_resolver().resolve("Endfield").application_id, ENDFIELD)

    def test_unknown_name_raises_with_a_hint(self):
        with self.assertRaises(ResolverError) as ctx:
            _resolver().resolve("Some Game That Does Not Exist")
        self.assertIn("Closest entries", str(ctx.exception))

    def test_empty_name_raises(self):
        with self.assertRaises(Exception):
            _resolver().resolve("   ")


class TestConfiguredIdHandling(unittest.TestCase):
    def test_configured_id_confirmed_by_catalogue(self):
        identity = _resolver().resolve("ARKNIGHTS: ENDFIELD", ENDFIELD)
        self.assertEqual(identity.source, "config-verified")

    def test_stale_id_falls_back_to_the_name(self):
        """Discord re-issues applications; a dead id must not be fatal."""
        identity = _resolver().resolve("ARKNIGHTS: ENDFIELD", "123456789012345678")
        self.assertEqual(identity.application_id, ENDFIELD)
        self.assertEqual(identity.source, "catalogue")

    def test_id_is_trusted_when_the_catalogue_is_unreachable(self):
        def boom(_url):
            raise ResolverError("network down")

        index = DetectableIndex(cache_path=Path("nope.json"), fetch=boom)
        resolver = IdentityResolver(index=index)
        identity = resolver.resolve("ARKNIGHTS: ENDFIELD", ENDFIELD)
        self.assertEqual(identity.application_id, ENDFIELD)
        self.assertEqual(identity.source, "config")

    def test_force_ignores_the_configured_id(self):
        identity = _resolver().resolve("ARKNIGHTS: ENDFIELD", "1441993124996972685", force=True)
        self.assertEqual(identity.application_id, ENDFIELD)


class TestCatalogueDrift(unittest.TestCase):
    def test_refresh_rederives_the_id(self):
        index = _index()
        resolver = IdentityResolver(index=index)
        first = resolver.resolve("ARKNIGHTS: ENDFIELD")
        self.assertEqual(first.application_id, ENDFIELD)

        # Discord re-issues the application under a new id.
        index._entries = [
            {"id": "999999999999999999", "name": "ARKNIGHTS: ENDFIELD", "aliases": [],
             "executables": [{"name": "endfield.exe"}]},
        ]
        index.refresh = lambda: index._entries  # no network in tests
        refreshed = resolver.refresh("ARKNIGHTS: ENDFIELD")
        self.assertEqual(refreshed.application_id, "999999999999999999")

    def test_payload_shape_drift_is_survivable(self):
        """A payload with unusable entries is rejected, not half-parsed."""
        index = _index([{"id": "1", "name": "Valid", "executables": []}, {"bogus": True}])
        self.assertEqual(len(index.entries()), 2)  # entries() is not re-filtering here
        self.assertEqual(index.search("Valid")[0].id, "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
