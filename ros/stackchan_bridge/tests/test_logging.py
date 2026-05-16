from __future__ import annotations

import logging
import unittest

from stackchan_bridge.logging import log_structured


class RclpyLikeLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def warning(self, message: str) -> None:
        self.messages.append(message)

    def log(self, message: str, severity: int) -> None:
        raise AssertionError("rclpy-style log should not be used before warning")


class StructuredLoggingTests(unittest.TestCase):
    def test_prefers_warning_method_for_rclpy_like_logger(self) -> None:
        logger = RclpyLikeLogger()

        log_structured(logger, logging.WARNING, "command_rejected", text="secret")

        self.assertEqual(len(logger.messages), 1)
        self.assertIn("command_rejected", logger.messages[0])
        self.assertIn("<redacted>", logger.messages[0])


if __name__ == "__main__":
    unittest.main()
