"""Command routing for system & media control and timers/reminders —
everything mocked, no real hardware touched."""

import unittest
from unittest.mock import patch

from _bootstrap import make_assistant


class SystemCommandTests(unittest.TestCase):
    def setUp(self):
        self.assistant = make_assistant()

    def spoken(self):
        return " ".join(self.assistant.tts.messages).lower()

    # -- volume -------------------------------------------------------------
    def test_volume_up(self):
        with patch("core.assistant.volume_up", return_value=True):
            self.assertTrue(self.assistant.handle_command("volume up"))
        self.assertIn("volume up", self.spoken())

    def test_turn_up_the_volume(self):
        with patch("core.assistant.volume_up", return_value=True):
            self.assertTrue(
                self.assistant.handle_command("turn up the volume"))
        self.assertIn("volume up", self.spoken())

    def test_volume_down(self):
        with patch("core.assistant.volume_down", return_value=True):
            self.assertTrue(self.assistant.handle_command("volume down"))
        self.assertIn("volume down", self.spoken())

    def test_set_volume_level(self):
        with patch("core.assistant.set_volume", return_value=True) as setv:
            self.assertTrue(
                self.assistant.handle_command("set volume to 50 percent"))
        setv.assert_called_once_with(50)
        self.assertIn("50 percent", self.spoken())

    def test_set_volume_unavailable(self):
        with patch("core.assistant.set_volume", return_value=False):
            self.assertTrue(
                self.assistant.handle_command("set volume to 50"))
        self.assertIn("can't set an exact volume", self.spoken())

    # -- mute ---------------------------------------------------------------
    def test_mute(self):
        with patch("core.assistant.set_mute", return_value=True) as sm:
            self.assertTrue(self.assistant.handle_command("mute"))
        sm.assert_called_once_with(True)
        self.assertIn("muted", self.spoken())

    def test_unmute(self):
        with patch("core.assistant.set_mute", return_value=True) as sm:
            self.assertTrue(self.assistant.handle_command("unmute"))
        sm.assert_called_once_with(False)
        self.assertIn("unmuted", self.spoken())

    # -- lock / battery -----------------------------------------------------
    def test_lock_pc(self):
        with patch("core.assistant.lock_workstation", return_value=True):
            self.assertTrue(self.assistant.handle_command("lock the pc"))
        self.assertIn("locking", self.spoken())

    def test_battery_percentage(self):
        with patch("core.assistant.battery_status",
                   return_value=(80, False)):
            self.assertTrue(
                self.assistant.handle_command("battery percentage"))
        self.assertIn("80 percent on battery", self.spoken())

    def test_battery_charging(self):
        with patch("core.assistant.battery_status",
                   return_value=(64, True)):
            self.assertTrue(self.assistant.handle_command("battery level"))
        self.assertIn("charging", self.spoken())

    def test_battery_no_battery(self):
        with patch("core.assistant.battery_status", return_value=None):
            self.assertTrue(self.assistant.handle_command("battery level"))
        self.assertIn("can't read a battery", self.spoken())

    # -- media keys ---------------------------------------------------------
    def test_next_track(self):
        with patch("core.assistant.media_next", return_value=True):
            self.assertTrue(self.assistant.handle_command("next track"))
        self.assertIn("skipping", self.spoken())

    def test_previous_track(self):
        with patch("core.assistant.media_previous", return_value=True):
            self.assertTrue(self.assistant.handle_command("previous song"))
        self.assertIn("going back", self.spoken())

    def test_pause(self):
        with patch("core.assistant.media_play_pause", return_value=True) as mp:
            self.assertTrue(self.assistant.handle_command("pause"))
        mp.assert_called_once()

    def test_play_music_goes_to_media_not_youtube(self):
        with patch("core.assistant.media_play_pause", return_value=True) as mp, \
                patch("core.assistant.play_on_youtube") as yt:
            self.assertTrue(self.assistant.handle_command("play music"))
        mp.assert_called_once()
        yt.assert_not_called()

    def test_play_song_on_youtube_still_works(self):
        with patch("core.assistant.media_play_pause") as mp, \
                patch("core.assistant.play_on_youtube") as yt:
            self.assertTrue(
                self.assistant.handle_command("play despacito on youtube"))
        mp.assert_not_called()
        yt.assert_called_once_with("despacito")

    def test_play_news_on_youtube_goes_to_youtube_not_news(self):
        """A 'play X on youtube' request must reach YouTube even when X
        contains a quick-command keyword ('news', 'weather', 'joke'...)."""
        with patch("core.assistant.play_on_youtube") as yt, \
                patch.object(self.assistant, "report_news") as news, \
                patch("core.assistant.have_internet", return_value=True):
            self.assertTrue(
                self.assistant.handle_command("play some news on youtube"))
        yt.assert_called_once()
        news.assert_not_called()

    def test_stop_music(self):
        with patch("core.assistant.media_stop", return_value=True) as ms:
            self.assertTrue(self.assistant.handle_command("stop the music"))
        ms.assert_called_once()


class TimerCommandTests(unittest.TestCase):
    def setUp(self):
        self.assistant = make_assistant()
        self.assistant.timers.cancel_all()

    def spoken(self):
        return " ".join(self.assistant.tts.messages).lower()

    def test_set_timer(self):
        self.assertTrue(
            self.assistant.handle_command("set a timer for 10 minutes"))
        self.assertIn("timer set for 10 minutes", self.spoken())
        self.assertEqual(len(self.assistant.timers.list()), 1)

    def test_remind_me_in(self):
        self.assertTrue(
            self.assistant.handle_command(
                "remind me to call dad in 5 minutes"))
        self.assertIn("call dad", self.spoken())
        items = self.assistant.timers.list()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][1], "⏰ Reminder: call dad")

    def test_remind_me_asks_for_time(self):
        with patch.object(self.assistant, "listen", return_value="in 10 minutes"):
            self.assertTrue(self.assistant.handle_command("remind me to call dad"))
        self.assertIn("done", self.spoken())
        self.assertEqual(len(self.assistant.timers.list()), 1)

    def test_remind_me_bad_time(self):
        with patch.object(self.assistant, "listen", return_value="tomorrow"):
            self.assertTrue(self.assistant.handle_command("remind me to call dad"))
        self.assertIn("didn't catch the time", self.spoken())
        self.assertEqual(self.assistant.timers.list(), [])

    def test_what_timers(self):
        self.assistant.timers.add(600, "⏰ Reminder: call dad")
        self.assertTrue(self.assistant.handle_command("what timers are active"))
        self.assertIn("call dad", self.spoken())

    def test_no_timers(self):
        self.assertTrue(self.assistant.handle_command("any reminders"))
        self.assertIn("no timers", self.spoken())

    def test_cancel_timers(self):
        self.assistant.timers.add(600, "⏰ Reminder: call dad")
        self.assertTrue(self.assistant.handle_command("cancel all timers"))
        self.assertEqual(self.assistant.timers.list(), [])
        self.assertIn("cleared", self.spoken())

    def test_plain_chat_still_not_a_command(self):
        self.assertFalse(self.assistant.handle_command("how are you"))


if __name__ == "__main__":
    unittest.main()
