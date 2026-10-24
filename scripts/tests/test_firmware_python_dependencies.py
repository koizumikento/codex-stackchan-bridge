from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from scripts import firmware_platformio


class FirmwarePythonDependencyTests(unittest.TestCase):
    def test_host_and_nested_installs_keep_security_floors(self) -> None:
        with (
            mock.patch.object(firmware_platformio, "sync_stackchan_msgs"),
            mock.patch.object(firmware_platformio, "patch_microros_platformio_meta"),
            mock.patch.object(firmware_platformio.subprocess, "run") as run,
        ):
            run.return_value.returncode = 7
            self.assertEqual(firmware_platformio.run_platformio(["--version"]), 7)

        command = run.call_args.args[0]
        constraints_path = run.call_args.kwargs["env"]["PIP_CONSTRAINT"]
        constraints = Path(constraints_path).read_text().splitlines()
        for requirement in ("pip>=26.2.2", "certifi>=2026.10.19"):
            with self.subTest(requirement=requirement):
                index = command.index(requirement)
                self.assertEqual(command[index - 1], "--with")
                self.assertIn(requirement, constraints)
        self.assertIn("empy==3.3.4", constraints)
        self.assertEqual(command[-2:], ["platformio", "--version"])
        self.assertEqual(run.call_args.kwargs["cwd"], firmware_platformio.ROOT)


if __name__ == "__main__":
    unittest.main()
