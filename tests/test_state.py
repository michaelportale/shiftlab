"""State persistence and clock handling.

The clock tests are the interesting ones: they are what stops `sudo date` from
being an off switch.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shiftd.state import (
    SOURCE_MONOTONIC,
    SOURCE_WALL_AFTER_REBOOT,
    StateStore,
)
from tests.support import FakeClock


class StateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="shiftd-state-"))
        self.path = self.dir / "nested" / "state.json"
        self.clock = FakeClock()
        self.store = StateStore(self.path, clock=self.clock)
        self.store.load()

    def start(self, duration_s=3600.0, locked=True):
        return self.store.start_shift(
            blocklist="social",
            rule="sleep",
            kind="schedule",
            locked=locked,
            profile_identifier="com.shiftd.block.social",
            duration_s=duration_s,
        )


class TestPersistence(StateTestCase):
    def test_roundtrip_survives_restart(self):
        self.start()
        self.store.mark_applied("abc123")
        self.store.save()

        reloaded = StateStore(self.path, clock=self.clock)
        reloaded.load()
        self.assertIsNotNone(reloaded.current)
        self.assertEqual(reloaded.current.blocklist, "social")
        self.assertTrue(reloaded.current.locked)
        self.assertEqual(reloaded.current.remaining_s, 3600.0)
        self.assertEqual(reloaded.current.content_hash, "abc123")
        self.assertTrue(reloaded.loaded_from_disk)

    def test_missing_file_is_empty_state_not_an_error(self):
        fresh = StateStore(self.dir / "does-not-exist.json", clock=self.clock)
        fresh.load()
        self.assertIsNone(fresh.current)
        self.assertFalse(fresh.loaded_from_disk)

    def test_save_is_atomic_and_leaves_no_temp_file(self):
        self.start()
        self.store.save()
        leftovers = [p.name for p in self.path.parent.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])
        self.assertTrue(json.loads(self.path.read_text())["current"]["locked"])

    def test_corrupt_state_is_preserved_and_reset(self):
        self.start()
        self.store.save()
        self.path.write_text("{ this is not json")

        recovered = StateStore(self.path, clock=self.clock)
        recovered.load()
        self.assertIsNone(recovered.current)
        backups = list(self.path.parent.glob("state.json.corrupt-*"))
        self.assertEqual(len(backups), 1)
        self.assertIn("state.corrupt", [entry["event"] for entry in recovered.state.history])

    def test_read_only_store_does_not_write(self):
        store = StateStore(self.path, clock=self.clock, read_only=True)
        store.load()
        store.start_shift(
            blocklist="social",
            rule="ad-hoc",
            kind="manual",
            locked=False,
            profile_identifier="com.shiftd.block.social",
            duration_s=60,
        )
        store.save()
        self.assertFalse(self.path.exists())


class TestClock(StateTestCase):
    def test_first_tick_credits_nothing(self):
        self.start()
        tick = self.store.tick()
        self.assertEqual(tick.elapsed_s, 0.0)
        self.assertEqual(self.store.current.remaining_s, 3600.0)

    def test_normal_time_decrements_budget(self):
        self.start()
        self.store.tick()
        self.clock.advance(600)
        tick = self.store.tick()
        self.assertEqual(tick.source, SOURCE_MONOTONIC)
        self.assertFalse(tick.jumped)
        self.assertEqual(self.store.current.remaining_s, 3000.0)

    def test_forward_clock_jump_credits_only_monotonic(self):
        """The 2am attack: set the Mac clock past the end of the window."""
        self.start(duration_s=3600.0)
        self.store.tick()
        self.clock.advance(60)
        self.clock.jump_wall(6 * 3600)  # wall only
        tick = self.store.tick()

        self.assertTrue(tick.jumped)
        self.assertEqual(tick.elapsed_s, 60.0)
        self.assertEqual(self.store.current.remaining_s, 3540.0)
        self.assertEqual(self.store.state.clock.jumps, 1)
        self.assertIn("clock.jump", [entry["event"] for entry in self.store.state.history])
        self.assertIsNotNone(self.store.locked_hold())

    def test_backward_clock_jump_does_not_extend_or_refund(self):
        self.start(duration_s=3600.0)
        self.store.tick()
        self.clock.advance(600)
        self.store.tick()
        self.assertEqual(self.store.current.remaining_s, 3000.0)

        self.clock.jump_wall(-7200)
        self.clock.advance(60)
        tick = self.store.tick()
        self.assertTrue(tick.jumped)
        self.assertEqual(self.store.current.remaining_s, 2940.0)

    def test_small_drift_is_not_reported_as_a_jump(self):
        self.start()
        self.store.tick()
        self.clock.advance(60)
        self.clock.jump_wall(5)  # an NTP correction
        tick = self.store.tick()
        self.assertFalse(tick.jumped)
        self.assertEqual(self.store.state.clock.jumps, 0)

    def test_reboot_falls_back_to_wall_clock(self):
        self.start(duration_s=3600.0)
        self.store.tick()
        self.store.save()

        self.clock.reboot(wall_gap=900.0, mono_start=5.0)
        after_reboot = StateStore(self.path, clock=self.clock)
        after_reboot.load()
        tick = after_reboot.tick()

        self.assertTrue(tick.rebooted)
        self.assertEqual(tick.source, SOURCE_WALL_AFTER_REBOOT)
        self.assertEqual(tick.elapsed_s, 900.0)
        self.assertEqual(after_reboot.current.remaining_s, 2700.0)
        self.assertEqual(after_reboot.state.clock.reboots, 1)

    def test_reboot_with_backwards_wall_clock_credits_nothing(self):
        self.start(duration_s=3600.0)
        self.store.tick()
        self.clock.jump_wall(-10_000)
        self.clock.reboot(wall_gap=0.0, mono_start=1.0)
        tick = self.store.tick()
        self.assertTrue(tick.rebooted)
        self.assertEqual(tick.elapsed_s, 0.0)
        self.assertEqual(self.store.current.remaining_s, 3600.0)

    def test_budget_floors_at_zero_and_releases_the_lock(self):
        self.start(duration_s=600.0)
        self.store.tick()
        self.clock.advance(10_000)
        self.store.tick()
        self.assertEqual(self.store.current.remaining_s, 0.0)
        self.assertTrue(self.store.current.expired)
        self.assertIsNone(self.store.locked_hold())

    def test_ends_at_tracks_the_budget_not_the_wall_clock(self):
        self.start(duration_s=3600.0)
        self.store.tick()
        self.clock.advance(60)
        self.clock.jump_wall(6 * 3600)
        self.store.tick()
        # ends_at is now + remaining, in whatever the wall clock currently claims.
        self.assertAlmostEqual(
            self.store.current.ends_at - self.clock.wall(), 3540.0, places=3
        )

    def test_open_ended_shift_has_no_budget_to_decrement(self):
        self.start(duration_s=None, locked=False)
        self.store.tick()
        self.clock.advance(10_000)
        self.store.tick()
        self.assertTrue(self.store.current.open_ended)
        self.assertFalse(self.store.current.expired)


class TestHistory(StateTestCase):
    def test_transitions_are_recorded(self):
        self.start(locked=False)
        self.store.end_shift("unshift")
        events = [entry["event"] for entry in self.store.state.history]
        self.assertEqual(events[-2:], ["shift.start", "shift.end"])
        self.assertEqual(self.store.state.history[-1]["reason"], "unshift")

    def test_history_is_capped(self):
        for index in range(600):
            self.store.note("noise", index=index)
        self.store.save()
        reloaded = StateStore(self.path, clock=self.clock)
        reloaded.load()
        self.assertLessEqual(len(reloaded.state.history), 400)
        self.assertEqual(reloaded.state.history[-1]["index"], 599)


if __name__ == "__main__":
    unittest.main()
