from __future__ import annotations

import importlib.util
import pathlib
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "serial_tcp_bridge.py"


def load_module():
    spec = importlib.util.spec_from_file_location("serial_tcp_bridge", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load serial_tcp_bridge module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSerial:
    def __init__(self) -> None:
        self.history = []
        self.port = None
        self.baudrate = None
        self.timeout = None
        self.write_timeout = None
        self.dtr = None
        self.rts = None
        self.opened = False
        self.open_dtr = None
        self.open_rts = None

    def __setattr__(self, name, value) -> None:
        object.__setattr__(self, name, value)
        if name in {"dtr", "rts"} and "history" in self.__dict__:
            self.history.append((name, value))

    def open(self) -> None:
        self.opened = True
        self.open_dtr = self.dtr
        self.open_rts = self.rts


class SerialTcpBridgeTests(unittest.TestCase):
    def test_open_serial_port_defaults_control_lines_inactive(self) -> None:
        module = load_module()
        fake = FakeSerial()
        module.serial.Serial = lambda: fake

        result = module.open_serial_port(
            types.SimpleNamespace(
                serial_port="COM3",
                baud=921600,
                dtr="inactive",
                rts="inactive",
                reset_pulse="none",
                reset_pulse_seconds=0.0,
                reset_settle_seconds=0.0,
            )
        )

        self.assertIs(result, fake)
        self.assertTrue(fake.opened)
        self.assertEqual(fake.port, "COM3")
        self.assertEqual(fake.baudrate, 921600)
        self.assertEqual(fake.timeout, 0)
        self.assertEqual(fake.write_timeout, 1)
        self.assertFalse(fake.open_dtr)
        self.assertFalse(fake.open_rts)

    def test_open_serial_port_can_leave_control_lines_unchanged(self) -> None:
        module = load_module()
        fake = FakeSerial()
        module.serial.Serial = lambda: fake

        module.open_serial_port(
            types.SimpleNamespace(
                serial_port="COM3",
                baud=921600,
                dtr="unchanged",
                rts="unchanged",
                reset_pulse="none",
                reset_pulse_seconds=0.0,
                reset_settle_seconds=0.0,
            )
        )

        self.assertTrue(fake.opened)
        self.assertIsNone(fake.open_dtr)
        self.assertIsNone(fake.open_rts)

    def test_open_serial_port_can_pulse_rts_after_open(self) -> None:
        module = load_module()
        fake = FakeSerial()
        module.serial.Serial = lambda: fake

        module.open_serial_port(
            types.SimpleNamespace(
                serial_port="COM3",
                baud=921600,
                dtr="inactive",
                rts="inactive",
                reset_pulse="rts",
                reset_pulse_seconds=0.0,
                reset_settle_seconds=0.0,
            )
        )

        self.assertTrue(fake.opened)
        self.assertFalse(fake.open_rts)
        self.assertEqual(fake.history[-2:], [("rts", True), ("rts", False)])
        self.assertFalse(fake.rts)

    def test_write_all_retries_partial_serial_writes(self) -> None:
        module = load_module()

        class PartialWriter:
            def __init__(self) -> None:
                self.calls = []

            def write(self, data) -> int:
                payload = bytes(data)
                self.calls.append(payload)
                return min(len(payload), 2)

        writer = PartialWriter()

        count = module.write_all(writer, b"abcdef")

        self.assertEqual(count, 6)
        self.assertEqual(writer.calls, [b"abcdef", b"cdef", b"ef"])


if __name__ == "__main__":
    unittest.main()
