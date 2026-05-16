from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class RuntimeConfig:
    backend: str = "bridge"
    device: str = "default"
    output: str = "human"
    log_level: str = "WARNING"
    timeout: float = 5.0
    source: str = "human_cli"


def _config_path(env: Mapping[str, str]) -> Path:
    xdg_home = env.get("XDG_CONFIG_HOME")
    if xdg_home:
        return Path(xdg_home) / "stackchanctl" / "config.toml"
    return Path.home() / ".config" / "stackchanctl" / "config.toml"


def load_config(env: Mapping[str, str] | None = None) -> RuntimeConfig:
    if env is None:
        env = os.environ
    path = _config_path(env)
    values: dict[str, object] = {}
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError:
        raw = {}
    except tomllib.TOMLDecodeError:
        raw = {}

    if isinstance(raw, dict):
        values.update(raw)

    return RuntimeConfig(
        backend=str(values.get("backend", values.get("default_backend", "bridge"))),
        device=str(values.get("device", values.get("default_device", "default"))),
        output=str(values.get("output", "human")),
        log_level=str(values.get("log_level", "WARNING")),
        timeout=float(values.get("timeout", 5.0)),
        source=str(values.get("source", "human_cli")),
    )


def resolve_runtime_config(
    *,
    cli_backend: str | None,
    cli_device: str | None,
    cli_json: bool,
    cli_source: str | None,
    cli_timeout: float | None,
    env: Mapping[str, str] | None = None,
) -> RuntimeConfig:
    if env is None:
        env = os.environ
    file_config = load_config(env)
    output = env.get("STACKCHANCTL_OUTPUT", file_config.output).lower()
    if cli_json:
        output = "json"

    return RuntimeConfig(
        backend=cli_backend
        or env.get("STACKCHANCTL_BACKEND")
        or file_config.backend
        or "bridge",
        device=cli_device
        or env.get("STACKCHANCTL_DEVICE")
        or file_config.device
        or "default",
        output=output,
        log_level=env.get("STACKCHANCTL_LOG_LEVEL", file_config.log_level),
        timeout=cli_timeout if cli_timeout is not None else file_config.timeout,
        source=cli_source
        or env.get("STACKCHANCTL_SOURCE")
        or file_config.source
        or "human_cli",
    )
