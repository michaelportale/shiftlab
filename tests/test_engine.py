"""Scheduler and reconcile loop, with the phone mocked out.

Covers the four things that would actually bite: a window that crosses
midnight, a locked shift that must not end early, reconcile running every
minute forever without stacking profiles, and a phone that is not there.
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from shiftd import profiles
from shiftd.engine import Engine, EngineError, LockedShiftActive, schedule_remaining
from shiftd.state import StateStore
from shiftd.transport import Transport
from tests.support import FakeClock, FakeTransport, make_config

SOCIAL = profiles.identifier_for("social")
GAMES = profiles.identifier_for("games")

SLEEP_RULE = {
    "name": "sleep",
    "kind": "schedule",
    "blocklist": "social",
    "days": "daily",
    "start": "22:30",
    "end": "07:00",
    "locked": True,
}
WORKDAY_RULE = {
    "name": "workday",
    "kind": "schedule",
    "blocklist": "social",
    "days": ["mon", "tue", "wed", "thu", "fri"],
    "start": "09:00",
    "end": "12:30",
    "locked": False,
}
DEEP_WORK_RULE = {
    "name": "deep-work",
    "kind": "session",
    "blocklist": "social",
    "duration": "90m",
    "locked": False,
}


def local(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M")


class EngineTestCase(unittest.TestCase):
    def build(self, rules=None, installed=None, reachable=True, at="2026-09-15 12:00"):
        self.dir = Path(tempfile.mkdtemp(prefix="shiftd-engine-"))
        self.clock = FakeClock()
        self.clock.set_local(at)
        self.config = make_config(rules if rules is not None else [SLEEP_RULE])
        self.store = StateStore(self.dir / "state.json", clock=self.clock)
        self.store.load()
        self.transport = FakeTransport(reachable=reachable, installed=installed)
        self.engine = Engine(
            self.config,
            self.store,
            self.transport,
            clock=self.clock,
            profile_dir=self.dir / "profiles",
        )
        return self.engine


# ---------------------------------------------------------------------------
# schedule maths
# ---------------------------------------------------------------------------

class TestScheduleWindows(EngineTestCase):
    def setUp(self):
        self.build()
        self.sleep = self.config.rule("sleep")
        self.workday = make_config([WORKDAY_RULE]).rule("workday")

    def test_inactive_one_minute_before_start(self):
        self.assertIsNone(schedule_remaining(self.sleep, local("2026-09-15 22:29")))

    def test_active_exactly_at_start(self):
        remaining = schedule_remaining(self.sleep, local("2026-09-15 22:30"))
        self.assertEqual(remaining, 8.5 * 3600)

    def test_active_after_midnight_belongs_to_the_previous_day(self):
        remaining = schedule_remaining(self.sleep, local("2026-09-16 02:00"))
        self.assertEqual(remaining, 5 * 3600)

    def test_last_minute_of_the_window_is_still_active(self):
        self.assertEqual(schedule_remaining(self.sleep, local("2026-09-16 06:59")), 60)

    def test_inactive_exactly_at_end(self):
        self.assertIsNone(schedule_remaining(self.sleep, local("2026-09-16 07:00")))

    def test_crossing_midnight_uses_the_starting_day_for_day_matching(self):
        friday_only = make_config(
            [dict(SLEEP_RULE, name="fri-night", days=["fri"])]
        ).rule("fri-night")
        # Friday 23:00, inside the window that started Friday.
        self.assertIsNotNone(schedule_remaining(friday_only, local("2026-09-18 23:00")))
        # Saturday 02:00, still the Friday window.
        self.assertIsNotNone(schedule_remaining(friday_only, local("2026-09-19 02:00")))
        # Saturday 23:00 is a Saturday window, which this rule does not have.
        self.assertIsNone(schedule_remaining(friday_only, local("2026-09-19 23:00")))
        # Sunday 02:00 would be the Saturday window. Also not this rule.
        self.assertIsNone(schedule_remaining(friday_only, local("2026-09-20 02:00")))

    def test_same_day_window_does_not_wrap(self):
        self.assertIsNotNone(schedule_remaining(self.workday, local("2026-09-15 09:00")))
        self.assertIsNone(schedule_remaining(self.workday, local("2026-09-15 12:30")))
        self.assertIsNone(schedule_remaining(self.workday, local("2026-09-15 20:00")))
        # Saturday is not a weekday.
        self.assertIsNone(schedule_remaining(self.workday, local("2026-09-19 10:00")))

    def test_disabled_rule_never_matches(self):
        off = make_config([dict(SLEEP_RULE, enabled=False)]).rule("sleep")
        self.assertIsNone(schedule_remaining(off, local("2026-09-15 23:00")))

    def test_locked_rule_wins_over_a_longer_unlocked_one(self):
        engine = self.build(
            rules=[
                dict(WORKDAY_RULE, name="long", blocklist="games", start="08:00", end="23:00"),
                dict(SLEEP_RULE, name="short-locked", start="09:00", end="10:00", blocklist="social"),
            ],
            at="2026-09-15 09:30",
        )
        active = engine.active_schedule()
        self.assertIsNotNone(active)
        self.assertEqual(active[0].name, "short-locked")


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------

class TestReconcile(EngineTestCase):
    def test_no_window_means_nothing_installed(self):
        engine = self.build(at="2026-09-15 12:00")
        report = engine.reconcile()
        self.assertIsNone(report.target)
        self.assertEqual(self.transport.installs, [])
        self.assertIsNone(engine.store.current)

    def test_window_start_installs_the_profile(self):
        engine = self.build(at="2026-09-15 22:31")
        report = engine.reconcile()
        self.assertEqual(report.target.blocklist, "social")
        self.assertTrue(report.target.locked)
        self.assertEqual(self.transport.installs, [SOCIAL])
        self.assertTrue(engine.store.current.applied)
        self.assertTrue(engine.store.current.locked)

    def test_reconcile_is_idempotent(self):
        engine = self.build(at="2026-09-15 22:31")
        engine.reconcile()
        for _ in range(5):
            self.clock.advance(60)
            report = engine.reconcile()
        self.assertEqual(self.transport.count_installs(SOCIAL), 1)
        self.assertEqual(self.transport.removals, [])
        self.assertFalse(report.changed)

    def test_profile_deleted_behind_our_back_is_reasserted(self):
        engine = self.build(at="2026-09-15 22:31")
        engine.reconcile()
        self.transport.drop_profile(SOCIAL)
        self.clock.advance(60)
        report = engine.reconcile()
        self.assertEqual(self.transport.count_installs(SOCIAL), 2)
        self.assertTrue(report.changed)

    def test_stale_profile_from_another_blocklist_is_removed(self):
        engine = self.build(at="2026-09-15 22:31", installed={GAMES})
        engine.reconcile()
        self.assertIn(GAMES, self.transport.removals)
        self.assertEqual(self.transport.installs, [SOCIAL])

    def test_window_end_removes_the_profile(self):
        engine = self.build(at="2026-09-15 22:31")
        engine.reconcile()
        self.clock.advance(8.5 * 3600)  # past 07:00
        report = engine.reconcile()
        self.assertIsNone(report.target)
        self.assertIsNone(engine.store.current)
        self.assertEqual(self.transport.removals, [SOCIAL])
        self.assertNotIn(SOCIAL, self.transport.installed)

    def test_content_change_reinstalls_once(self):
        engine = self.build(at="2026-09-15 22:31")
        engine.reconcile()
        bigger = make_config([SLEEP_RULE])
        bigger.blocklists["social"] = ("com.burbn.instagram", "com.reddit.Reddit", "tv.twitch")
        engine.config = bigger
        self.clock.advance(60)
        engine.reconcile()
        self.assertEqual(self.transport.count_installs(SOCIAL), 2)
        self.clock.advance(60)
        engine.reconcile()
        self.assertEqual(self.transport.count_installs(SOCIAL), 2)


class TestUnreachableDevice(EngineTestCase):
    def test_unreachable_phone_does_not_raise_and_keeps_the_shift(self):
        engine = self.build(at="2026-09-15 22:31", reachable=False)
        report = engine.reconcile()
        self.assertTrue(report.ok)
        self.assertFalse(report.device_reachable)
        self.assertIsNotNone(engine.store.current)
        self.assertFalse(engine.store.current.applied)
        self.assertGreaterEqual(engine.store.current.apply_attempts, 1)

    def test_profile_is_asserted_when_the_phone_comes_back(self):
        engine = self.build(at="2026-09-15 22:31", reachable=False)
        for _ in range(3):
            engine.reconcile()
            self.clock.advance(60)
        self.assertEqual(self.transport.installs, [])

        self.transport.reachable_flag = True
        report = engine.reconcile()
        self.assertEqual(self.transport.installs, [SOCIAL])
        self.assertTrue(engine.store.current.applied)
        self.assertTrue(report.device_reachable)

    def test_time_served_still_counts_while_unreachable(self):
        engine = self.build(at="2026-09-15 22:31", reachable=False)
        engine.reconcile()
        remaining_at_start = engine.store.current.remaining_s
        self.clock.advance(3600)
        engine.reconcile()
        self.assertAlmostEqual(engine.store.current.remaining_s, remaining_at_start - 3600, places=3)

    def test_a_real_failure_is_reported_not_swallowed(self):
        engine = self.build(at="2026-09-15 22:31")
        self.transport.fail_install = "MCInstallationErrorDomain 4001"
        report = engine.reconcile()
        self.assertFalse(report.ok)
        self.assertTrue(any("4001" in error for error in report.errors))


class TestLockedShift(EngineTestCase):
    def test_unshift_is_refused_while_locked(self):
        engine = self.build(at="2026-09-15 22:31")
        engine.reconcile()
        with self.assertRaises(LockedShiftActive) as caught:
            engine.unshift()
        self.assertIn("locked", str(caught.exception))
        self.assertIsNotNone(engine.store.current)
        self.assertIn(SOCIAL, self.transport.installed)

    def test_starting_another_shift_is_refused_while_locked(self):
        engine = self.build(at="2026-09-15 22:31")
        engine.reconcile()
        with self.assertRaises(LockedShiftActive):
            engine.start("games", duration_s=600)

    def test_clock_jump_past_the_window_does_not_end_a_locked_shift(self):
        engine = self.build(at="2026-09-15 22:31")
        engine.reconcile()
        self.clock.advance(60)
        engine.reconcile()

        # `sudo date 0900` at 23:32.
        self.clock.jump_wall(10 * 3600)
        report = engine.reconcile()

        self.assertTrue(report.clock_jumped)
        self.assertIsNotNone(engine.store.current)
        self.assertTrue(engine.store.current.locked)
        self.assertEqual(report.target.blocklist, "social")
        self.assertIn(SOCIAL, self.transport.installed)
        self.assertEqual(self.transport.removals, [])

    def test_locked_shift_ends_when_the_budget_is_actually_served(self):
        engine = self.build(at="2026-09-15 22:31")
        engine.reconcile()
        self.clock.advance(8.5 * 3600)
        engine.reconcile()
        self.assertIsNone(engine.store.current)
        self.assertNotIn(SOCIAL, self.transport.installed)

    def test_locked_shift_survives_a_daemon_restart(self):
        engine = self.build(at="2026-09-15 22:31")
        engine.reconcile()

        restarted_store = StateStore(self.store.path, clock=self.clock)
        restarted_store.load()
        restarted = Engine(
            self.config, restarted_store, self.transport, clock=self.clock,
            profile_dir=self.dir / "profiles",
        )
        with self.assertRaises(LockedShiftActive):
            restarted.unshift()

    def test_deleting_the_rule_from_config_does_not_release_a_locked_shift(self):
        engine = self.build(at="2026-09-15 22:31")
        engine.reconcile()
        engine.config = make_config([])  # rule gone
        self.clock.advance(60)
        report = engine.reconcile()
        self.assertEqual(report.target.blocklist, "social")
        self.assertIsNotNone(engine.store.current)


class TestManualShifts(EngineTestCase):
    def test_shift_by_blocklist_name(self):
        engine = self.build(rules=[], at="2026-09-15 12:00")
        engine.start("social", duration_s=90 * 60)
        report = engine.reconcile()
        self.assertEqual(report.target.rule, "ad-hoc")
        self.assertEqual(self.transport.installs, [SOCIAL])

    def test_shift_by_rule_name_uses_the_rule_defaults(self):
        engine = self.build(rules=[DEEP_WORK_RULE], at="2026-09-15 12:00")
        shift = engine.start("deep-work")
        self.assertEqual(shift.remaining_s, 90 * 60)
        self.assertFalse(shift.locked)

    def test_unlocked_shift_can_be_ended_early(self):
        engine = self.build(rules=[], at="2026-09-15 12:00")
        engine.start("social", duration_s=3600)
        engine.reconcile()
        engine.unshift()
        report = engine.reconcile()
        self.assertIsNone(report.target)
        self.assertEqual(self.transport.removals, [SOCIAL])

    def test_unknown_name_is_a_clear_error(self):
        engine = self.build(rules=[], at="2026-09-15 12:00")
        with self.assertRaises(EngineError) as caught:
            engine.start("nope")
        self.assertIn("nope", str(caught.exception))

    def test_open_ended_locked_shift_is_refused(self):
        engine = self.build(rules=[], at="2026-09-15 12:00")
        with self.assertRaises(EngineError):
            engine.start("social", duration_s=None, locked=True)

    def test_manual_shift_outlives_a_schedule_window_it_overlaps(self):
        engine = self.build(rules=[WORKDAY_RULE], at="2026-09-15 12:00")
        engine.start("games", duration_s=2 * 3600)
        report = engine.reconcile()
        self.assertEqual(report.target.blocklist, "games")
        self.clock.advance(1800)  # 12:30, workday window over anyway
        report = engine.reconcile()
        self.assertEqual(report.target.blocklist, "games")


class TestDryRun(EngineTestCase):
    def test_dry_run_touches_neither_the_phone_nor_the_state_file(self):
        self.build(at="2026-09-15 22:31")
        store = StateStore(self.dir / "dry-state.json", clock=self.clock, read_only=True)
        store.load()
        engine = Engine(
            self.config,
            store,
            Transport(udid="X", dry_run=True),
            clock=self.clock,
            profile_dir=self.dir / "profiles",
        )
        report = engine.reconcile(dry_run=True)
        self.assertEqual(report.target.blocklist, "social")
        self.assertFalse((self.dir / "dry-state.json").exists())
        self.assertIn("would do", report.render())


if __name__ == "__main__":
    unittest.main()
