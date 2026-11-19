"""Root logger stays at WARNING (library spam), our loggers at INFO; Move replies on the response topic."""
import logging
import unittest

from controller import robot as R


class LoggingSetupTest(unittest.TestCase):
    def test_library_info_spam_is_dropped(self):
        from controller.app import setup_logging

        root = logging.getLogger()
        before = list(root.handlers)
        try:
            setup_logging()
            self.assertEqual(root.level, logging.WARNING)
            self.assertTrue(logging.getLogger("go2.ui").isEnabledFor(logging.INFO))
            # what unitree_webrtc_connect does for every datachannel message:
            self.assertFalse(root.isEnabledFor(logging.INFO))
        finally:
            for h in root.handlers[len(before):]:
                root.removeHandler(h)
                h.close()


class SportReplyTopicTest(unittest.TestCase):
    def test_move_reply_on_response_topic_is_recorded(self):
        self.assertEqual(R.SPORT_RESPONSE_TOPIC, "rt/api/sport/response")
        s = R.RobotSession()
        msg = {"type": "res", "topic": R.SPORT_RESPONSE_TOPIC,
               "data": {"header": {"identity": {"api_id": R.SPORT_CMD["Move"], "id": 1}, "status": {"code": 0}}}}
        s._on_sport_reply(msg)
        self.assertEqual(s._move_last_code, 0)
        s._loop.close()


if __name__ == "__main__":
    unittest.main()
