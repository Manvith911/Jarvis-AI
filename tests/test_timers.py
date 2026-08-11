"""Tests for core/timers.py — parsers, duration formatting, and the
TimerManager firing behaviour. No real time is waited beyond tiny delays."""

import threading
import time
import unittest

from core.timers import (
    TimerManager, format_duration, parse_reminder_command,
    parse_timer_command, seconds_until,
)


class ParseTimerTests(unittest.TestCase):
    def test_set_timer_for_minutes(self):
        self.assertEqual(parse_timer_command("set a timer for 10 minutes"),
                         (600, "minutes"))

    def test_timer_seconds(self):
        self.assertEqual(parse_timer_command("timer 30 seconds"),
                         (30, "seconds"))

    def test_set_timer_short_form(self):
        self.assertEqual(parse_timer_command("set timer 5 min"),
                         (300, "min"))

    def test_timer_before_form(self):
        self.assertEqual(parse_timer_command("10 minute timer"),
                         (600, "minute"))

    def test_hour_timer(self):
        self.assertEqual(parse_timer_command("set a timer for 1 hour"),
                         (3600, "hour"))

    def test_not_a_timer(self):
        self.assertIsNone(parse_timer_command("what time is it"))
        self.assertIsNone(parse_timer_command(""))
        self.assertIsNone(parse_timer_command("timer"))


class ParseReminderTests(unittest.TestCase):
    def test_remind_to_in(self):
        self.assertEqual(
            parse_reminder_command("remind me to call dad in 5 minutes"),
            ("call dad", 300))

    def test_remind_in_to(self):
        self.assertEqual(
            parse_reminder_command("remind me in 10 minutes to drink water"),
            ("drink water", 600))

    def test_remind_to_at_pm(self):
        task, seconds = parse_reminder_command("remind me to stretch at 5 pm")
        self.assertEqual(task, "stretch")
        # next 5 pm is tonight or tomorrow — within the next 24h
        self.assertGreater(seconds, 0)
        self.assertLess(seconds, 86400 + 60)

    def test_remind_at_to(self):
        task, seconds = parse_reminder_command(
            "remind me at 5:30 pm to call dad")
        self.assertEqual(task, "call dad")
        self.assertLess(seconds, 86400 + 60)

    def test_remind_in_with_no_task(self):
        self.assertEqual(parse_reminder_command("remind me in 2 minutes"),
                         ("", 120))

    def test_remind_no_time(self):
        self.assertIsNone(parse_reminder_command("remind me to call dad"))

    def test_not_a_reminder(self):
        self.assertIsNone(parse_reminder_command("what does remind mean"))
        self.assertIsNone(parse_reminder_command(""))


class SecondsUntilTests(unittest.TestCase):
    def test_future_time_positive(self):
        # 5 pm is never more than ~24h away
        self.assertGreater(seconds_until(17, 0, "pm"), 0)
        self.assertLess(seconds_until(17, 0, "pm"), 86400 + 60)

    def test_ampm_mapping(self):
        # each call samples 'now' microseconds apart — compare with tolerance
        self.assertAlmostEqual(seconds_until(9, 0, "am") % 86400,
                               seconds_until(9, 0) % 86400, places=1)
        self.assertAlmostEqual(seconds_until(12, 0, "pm") % 86400,
                               seconds_until(12, 0) % 86400, places=1)


class FormatDurationTests(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(format_duration(30), "30 seconds")
        self.assertEqual(format_duration(1), "1 second")

    def test_minutes(self):
        self.assertEqual(format_duration(600), "10 minutes")
        self.assertEqual(format_duration(60), "1 minute")

    def test_hours(self):
        self.assertEqual(format_duration(3600), "1 hour")
        self.assertEqual(format_duration(3900), "1 hour and 5 minutes")
        self.assertEqual(format_duration(7200), "2 hours")

    def test_rounds_fractional_seconds(self):
        """599.9s must speak '10 minutes', not truncate to '9 minutes'."""
        self.assertEqual(format_duration(599.9), "10 minutes")


class TimerManagerTests(unittest.TestCase):
    def test_fires_after_delay(self):
        fired = []
        event = threading.Event()

        def on_fire(msg):
            fired.append(msg)
            event.set()

        tm = TimerManager(on_fire=on_fire)
        tm.add(0.1, "ding")
        self.assertTrue(event.wait(2.0), "timer never fired")
        self.assertEqual(fired, ["ding"])

    def test_list_and_cancel(self):
        tm = TimerManager()
        tm.add(600, "a")
        tm.add(120, "b")
        items = tm.list()
        self.assertEqual(len(items), 2)
        self.assertAlmostEqual(items[0][0], 120, places=1)  # soonest first
        self.assertAlmostEqual(items[1][0], 600, places=1)
        tm.cancel_all()
        self.assertEqual(tm.list(), [])


if __name__ == "__main__":
    unittest.main()
