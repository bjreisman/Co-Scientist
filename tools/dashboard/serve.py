"""Shared dashboard supervisor for the standalone dashboard app runtime."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import urlopen

from packages.run_artifacts import ArtifactStore


class ProcessLike(Protocol):
    """Small protocol for launched background processes."""

    pid: int

    def poll(self) -> int | None:
        """Return the exit code when the process has already exited."""


@dataclass(frozen=True)
class DashboardRuntimeResult:
    """One dashboard runtime result with explicit readiness semantics."""

    runtime: dict[str, Any]
    ready: bool


def _now_epoch() -> float:
    return time.time()


def _platform_pnpm_command() -> str:
    return "pnpm.cmd" if os.name == "nt" else "pnpm"


def _http_is_healthy(url: str, timeout: float = 1.0) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310
            return 200 <= response.status < 500
    except URLError:
        return False
    except OSError:
        return False


def _port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _find_available_port(host: str, preferred_port: int) -> int:
    if _port_is_available(host, preferred_port):
        return preferred_port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class DashboardSupervisor:
    """Ensure the standalone dashboard app is available and record its runtime."""

    def __init__(
        self,
        runs_dir: Path,
        *,
        repo_root: Path | None = None,
        api_host: str = "127.0.0.1",
        frontend_host: str = "127.0.0.1",
        preferred_api_port: int = 8000,
        preferred_frontend_port: int = 3000,
        launcher: Any = None,
        health_checker: Any = None,
        wait_timeout_seconds: float = 30.0,
        background_wait_seconds: float = 2.0,
        startup_grace_seconds: float = 45.0,
    ) -> None:
        """Initialize dashboard runtime supervision settings."""
        self.runs_dir = runs_dir.resolve()
        self.repo_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
        self.api_host = api_host
        self.frontend_host = frontend_host
        self.preferred_api_port = preferred_api_port
        self.preferred_frontend_port = preferred_frontend_port
        self.launcher = launcher or self._launch_process
        self.health_checker = health_checker or _http_is_healthy
        self.wait_timeout_seconds = wait_timeout_seconds
        self.background_wait_seconds = background_wait_seconds
        self.startup_grace_seconds = startup_grace_seconds

    @property
    def runtime_path(self) -> Path:
        """Return the shared dashboard runtime metadata path."""
        return self.runs_dir / "_dashboard" / "runtime.json"

    def ensure_started(self, *, wait_for_health: bool = True) -> dict[str, Any]:
        """Ensure the dashboard app is available and return runtime metadata."""
        return self.ensure_started_with_status(wait_for_health=wait_for_health).runtime

    def ensure_started_with_status(self, *, wait_for_health: bool = True) -> DashboardRuntimeResult:
        """Ensure the dashboard app is available and return runtime metadata with readiness."""
        self.runtime_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_store = ArtifactStore(self.runs_dir / "__dashboard_runtime_placeholder__")
        current_runtime = artifact_store.read_dashboard_runtime() or self._default_runtime()

        current_frontend = current_runtime.get("frontend", {})
        current_frontend_base_url = str(
            current_frontend.get("baseUrl", f"http://{self.frontend_host}:{self.preferred_frontend_port}")
        )
        current_frontend_port = int(current_frontend.get("port", self.preferred_frontend_port))
        current_status = str(current_runtime.get("status", "not_started"))

        frontend_healthy = self.health_checker(f"{current_frontend_base_url.rstrip('/')}/api/health")
        if frontend_healthy:
            frontend_runtime = self._healthy_frontend_runtime(current_frontend, current_frontend_base_url)
            ready = True
        elif self._should_reuse_starting_runtime(current_runtime, current_frontend_port):
            frontend_runtime = self._starting_frontend_runtime(current_frontend, current_frontend_base_url)
            ready = False
            current_status = "starting"
        else:
            frontend_port = _find_available_port(self.frontend_host, current_frontend_port)
            launch_result = self._start_frontend(frontend_port, wait_for_health=wait_for_health)
            frontend_runtime = launch_result.runtime
            ready = launch_result.ready
            current_status = "running" if ready else str(frontend_runtime.get("status", "starting"))

        runtime = {
            "updatedAt": _now_epoch(),
            "status": current_status,
            "api": self._embedded_api_runtime(
                str(frontend_runtime["baseUrl"]),
                status="running" if ready else "starting",
                port=int(frontend_runtime["port"]),
            ),
            "frontend": frontend_runtime,
        }
        artifact_store.write_dashboard_runtime(runtime)
        return DashboardRuntimeResult(runtime=runtime, ready=ready)

    def build_run_links(self, run_id: str, runtime: dict[str, Any]) -> dict[str, str]:
        """Build the main dashboard link plus stable deep links for one run."""
        frontend_base = str(runtime["frontend"]["baseUrl"]).rstrip("/")
        return {
            "dashboard": f"{frontend_base}/?run={run_id}",
            "ranking": f"{frontend_base}/ranking?run={run_id}",
            "evolution": f"{frontend_base}/evolution?run={run_id}",
            "metaReviews": f"{frontend_base}/meta-reviews?run={run_id}",
        }

    def _default_runtime(self) -> dict[str, Any]:
        frontend_base_url = f"http://{self.frontend_host}:{self.preferred_frontend_port}"
        return {
            "updatedAt": _now_epoch(),
            "status": "not_started",
            "api": self._embedded_api_runtime(
                frontend_base_url,
                status="not_started",
                port=self.preferred_frontend_port,
            ),
            "frontend": {
                "status": "not_started",
                "host": self.frontend_host,
                "port": self.preferred_frontend_port,
                "baseUrl": frontend_base_url,
            },
        }

    def _embedded_api_runtime(self, frontend_base_url: str, *, status: str = "running", port: int) -> dict[str, Any]:
        api_base_url = f"{str(frontend_base_url).rstrip('/')}/api"
        return {
            "status": status,
            "embedded": True,
            "baseUrl": api_base_url,
            "healthUrl": f"{api_base_url}/health",
            "host": self.frontend_host,
            "port": port,
        }

    def _healthy_frontend_runtime(self, current_runtime: dict[str, Any], base_url: str) -> dict[str, Any]:
        return {
            "status": "running",
            "host": current_runtime.get("host", self.frontend_host),
            "port": int(current_runtime.get("port", self.preferred_frontend_port)),
            "baseUrl": base_url,
            "pid": current_runtime.get("pid"),
            "command": current_runtime.get("command"),
            "healthUrl": f"{base_url.rstrip('/')}/api/health",
        }

    def _starting_frontend_runtime(self, current_runtime: dict[str, Any], base_url: str) -> dict[str, Any]:
        return {
            "status": "starting",
            "host": current_runtime.get("host", self.frontend_host),
            "port": int(current_runtime.get("port", self.preferred_frontend_port)),
            "baseUrl": base_url,
            "pid": current_runtime.get("pid"),
            "command": current_runtime.get("command"),
            "healthUrl": f"{base_url.rstrip('/')}/api/health",
        }

    def _should_reuse_starting_runtime(self, current_runtime: dict[str, Any], port: int) -> bool:
        if str(current_runtime.get("status", "")) != "starting":
            return False
        updated_at = float(current_runtime.get("updatedAt", 0.0) or 0.0)
        if (_now_epoch() - updated_at) > self.startup_grace_seconds:
            return False
        return not _port_is_available(self.frontend_host, port)

    def _start_frontend(self, port: int, *, wait_for_health: bool) -> DashboardRuntimeResult:
        base_url = f"http://{self.frontend_host}:{port}"
        env = os.environ.copy()
        env["CO_SCIENTIST_RUNS_DIR"] = str(self.runs_dir)
        frontend_dir = self.repo_root / "apps" / "dashboard"
        attempted_commands: list[list[str]] = []
        for command in self._frontend_commands(frontend_dir, port):
            attempted_commands.append(command)
            process = self.launcher(command, frontend_dir, env)
            try:
                self._wait_for_health(
                    f"{base_url}/api/health",
                    process=process,
                    command=command,
                    timeout_seconds=self.wait_timeout_seconds if wait_for_health else self.background_wait_seconds,
                )
                return DashboardRuntimeResult(
                    runtime={
                        "status": "running",
                        "host": self.frontend_host,
                        "port": port,
                        "baseUrl": base_url,
                        "pid": getattr(process, "pid", None),
                        "command": command,
                        "healthUrl": f"{base_url.rstrip('/')}/api/health",
                    },
                    ready=True,
                )
            except TimeoutError:
                if wait_for_health:
                    continue
                return DashboardRuntimeResult(
                    runtime={
                        "status": "starting",
                        "host": self.frontend_host,
                        "port": port,
                        "baseUrl": base_url,
                        "pid": getattr(process, "pid", None),
                        "command": command,
                        "healthUrl": f"{base_url.rstrip('/')}/api/health",
                    },
                    ready=False,
                )
            except RuntimeError:
                continue
        raise TimeoutError(
            "Dashboard service did not become healthy in time after trying: "
            + ", ".join(" ".join(command) for command in attempted_commands)
        )

    def _frontend_commands(self, frontend_dir: Path, port: int) -> list[list[str]]:
        pnpm_command = _platform_pnpm_command()
        preview_command = [
            pnpm_command,
            "preview",
            f"--host={self.frontend_host}",
            f"--port={port}",
        ]
        dev_command = [
            pnpm_command,
            "dev",
            "--host",
            self.frontend_host,
            "--port",
            str(port),
        ]
        output_dir = frontend_dir / ".output"
        if output_dir.exists():
            return [preview_command, dev_command]
        return [dev_command]

    def _wait_for_health(
        self,
        url: str,
        *,
        process: ProcessLike | None = None,
        command: list[str] | None = None,
        timeout_seconds: float,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if process is not None:
                poll = getattr(process, "poll", None)
                if callable(poll):
                    exit_code = poll()
                    if exit_code is not None:
                        command_text = " ".join(command or [])
                        raise RuntimeError(
                            f"Dashboard process exited before becoming healthy (exit={exit_code}): {command_text}"
                        )
            if self.health_checker(url):
                return
            time.sleep(0.25)
        raise TimeoutError(f"Dashboard service did not become healthy in time: {url}")

    def _launch_process(self, command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen[str]:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.Popen(  # noqa: S603
            command,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creation_flags,
        )


__all__ = ["DashboardRuntimeResult", "DashboardSupervisor"]
