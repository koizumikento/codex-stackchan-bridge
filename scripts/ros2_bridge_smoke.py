from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = os.environ.copy()
    stackchanctl_src = str(ROOT / "apps" / "stackchanctl" / "src")
    env["PYTHONPATH"] = (
        stackchanctl_src
        if not env.get("PYTHONPATH")
        else f"{stackchanctl_src}{os.pathsep}{env['PYTHONPATH']}"
    )

    node = subprocess.Popen(
        [
            _bridge_node_executable(env),
            "--ros-args",
            "-p",
            "device_connected:=false",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    failure: BaseException | None = None
    try:
        observe = _run_cli_until_ready(env)
        _assert_observe_disconnected(observe)

        face = _run_cli(
            env,
            [
                "--backend",
                "bridge",
                "--timeout",
                "2",
                "face",
                "happy",
                "--json",
            ],
        )
        _assert_transport_disconnected(face)
    except BaseException as exc:
        failure = exc
        raise
    finally:
        node.terminate()
        try:
            node.wait(timeout=5)
        except subprocess.TimeoutExpired:
            node.kill()
            node.wait(timeout=5)
        if failure is not None:
            stdout = node.stdout.read() if node.stdout is not None else ""
            stderr = node.stderr.read() if node.stderr is not None else ""
            print("stackchan_bridge_node stdout:", file=sys.stderr)
            print(stdout, file=sys.stderr)
            print("stackchan_bridge_node stderr:", file=sys.stderr)
            print(stderr, file=sys.stderr)

    print("bridge smoke passed: no-device path returns TRANSPORT_DISCONNECTED")
    return 0


def _bridge_node_executable(env: dict[str, str]) -> str:
    executable = shutil.which("stackchan_bridge_node", path=env.get("PATH"))
    if executable is not None:
        return executable

    installed = ROOT / "install" / "stackchan_bridge" / "lib" / "stackchan_bridge" / "stackchan_bridge_node"
    if installed.exists():
        return str(installed)

    raise FileNotFoundError(
        "stackchan_bridge_node is not available; run colcon build and source install/setup.bash"
    )


def _run_cli_until_ready(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    deadline = time.monotonic() + 15
    last: subprocess.CompletedProcess[str] | None = None
    while time.monotonic() < deadline:
        last = _run_cli(
            env,
            [
                "--backend",
                "bridge",
                "--timeout",
                "2",
                "observe",
                "--json",
            ],
        )
        if last.returncode == 0:
            return last
        time.sleep(0.5)

    assert last is not None
    raise RuntimeError(
        "stackchan_bridge_node did not answer observe before timeout\n"
        f"stdout:\n{last.stdout}\n"
        f"stderr:\n{last.stderr}"
    )


def _run_cli(
    env: dict[str, str], args: list[str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "stackchanctl", *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _assert_observe_disconnected(result: subprocess.CompletedProcess[str]) -> None:
    payload = json.loads(result.stdout)
    error = payload.get("last_error") or {}
    if payload.get("connected") is not False:
        raise AssertionError(f"expected disconnected observe payload: {payload}")
    if error.get("code") != "TRANSPORT_DISCONNECTED":
        raise AssertionError(f"expected TRANSPORT_DISCONNECTED status: {payload}")


def _assert_transport_disconnected(result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode == 0:
        raise AssertionError(f"expected bridge command rejection, got stdout={result.stdout}")
    payload = json.loads(result.stderr)
    error = payload.get("error") or {}
    if payload.get("ok") is not False:
        raise AssertionError(f"expected ok=false command result: {payload}")
    if payload.get("result_state") != "REJECTED":
        raise AssertionError(f"expected REJECTED command result: {payload}")
    if error.get("code") != "TRANSPORT_DISCONNECTED":
        raise AssertionError(f"expected TRANSPORT_DISCONNECTED error: {payload}")


if __name__ == "__main__":
    raise SystemExit(main())
