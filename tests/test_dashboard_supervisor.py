from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tools.dashboard.serve import DashboardSupervisor


class FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    def poll(self) -> int | None:
        return None


class FakeExitedProcess(FakeProcess):
    def __init__(self, pid: int, exit_code: int) -> None:
        super().__init__(pid)
        self.exit_code = exit_code

    def poll(self) -> int | None:
        return self.exit_code


def test_dashboard_supervisor_starts_services_and_reuses_runtime() -> None:
    with TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir) / "runs"
        repo_root = Path(temp_dir) / "repo"
        (repo_root / "apps" / "dashboard").mkdir(parents=True)
        runs_dir.mkdir()

        healthy_urls: set[str] = set()
        launched: list[tuple[list[str], Path, dict[str, str]]] = []

        def fake_launcher(command: list[str], cwd: Path, env: dict[str, str]) -> FakeProcess:
            launched.append((command, cwd, env))
            port = int(command[command.index("--port") + 1])
            healthy_urls.add(f"http://127.0.0.1:{port}/api/health")
            return FakeProcess(pid=1000 + len(launched))

        selected_ports = iter([3000])
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            "tools.dashboard.serve._find_available_port",
            lambda host, preferred_port: next(selected_ports),
        )
        try:
            supervisor = DashboardSupervisor(
                runs_dir,
                launcher=fake_launcher,
                health_checker=lambda url: url in healthy_urls,
            )

            runtime = supervisor.ensure_started()
            assert runtime["status"] == "running"
            assert runtime["api"]["baseUrl"] == "http://127.0.0.1:3000/api"
            assert runtime["api"]["embedded"] is True
            assert runtime["frontend"]["baseUrl"] == "http://127.0.0.1:3000"
            assert launched[0][1].as_posix().endswith("/apps/dashboard")
            assert launched[0][2]["CO_SCIENTIST_RUNS_DIR"] == str(runs_dir)
            assert "NUXT_PUBLIC_API_BASE" not in launched[0][2]

            runtime_payload = json.loads((runs_dir / "_dashboard" / "runtime.json").read_text(encoding="utf-8"))
            assert runtime_payload["status"] == "running"

            links = supervisor.build_run_links("demo-run", runtime)
            assert links["dashboard"].endswith("/?run=demo-run")
            assert links["ranking"].endswith("/ranking?run=demo-run")
            assert links["evolution"].endswith("/evolution?run=demo-run")
            assert links["metaReviews"].endswith("/meta-reviews?run=demo-run")

            second_runtime = supervisor.ensure_started()
            assert second_runtime["api"]["baseUrl"] == runtime["api"]["baseUrl"]
            assert second_runtime["frontend"]["baseUrl"] == runtime["frontend"]["baseUrl"]
            assert len(launched) == 1
        finally:
            monkeypatch.undo()


def test_dashboard_supervisor_uses_fallback_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    with TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir) / "runs"
        runs_dir.mkdir()

        healthy_urls: set[str] = set()

        def fake_launcher(command: list[str], cwd: Path, env: dict[str, str]) -> FakeProcess:
            port = int(command[command.index("--port") + 1])
            healthy_urls.add(f"http://127.0.0.1:{port}/api/health")
            return FakeProcess(pid=2000 + port)

        selected_ports = iter([3101])
        monkeypatch.setattr(
            "tools.dashboard.serve._find_available_port",
            lambda host, preferred_port: next(selected_ports),
        )

        supervisor = DashboardSupervisor(
            runs_dir,
            launcher=fake_launcher,
            health_checker=lambda url: url in healthy_urls,
        )
        runtime = supervisor.ensure_started()

        assert runtime["api"]["port"] == 3101
        assert runtime["frontend"]["port"] == 3101


def test_dashboard_supervisor_can_return_starting_runtime_without_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir) / "runs"
        repo_root = Path(temp_dir) / "repo"
        (repo_root / "apps" / "dashboard").mkdir(parents=True)
        runs_dir.mkdir()

        launched: list[list[str]] = []

        def fake_launcher(command: list[str], cwd: Path, env: dict[str, str]) -> FakeProcess:
            launched.append(command)
            return FakeProcess(pid=5001)

        monkeypatch.setattr(
            "tools.dashboard.serve._find_available_port",
            lambda host, preferred_port: 3000,
        )

        supervisor = DashboardSupervisor(
            runs_dir,
            repo_root=repo_root,
            launcher=fake_launcher,
            health_checker=lambda url: False,
            background_wait_seconds=0.01,
        )
        runtime = supervisor.ensure_started(wait_for_health=False)

        assert runtime["status"] == "starting"
        assert runtime["frontend"]["status"] == "starting"
        assert runtime["frontend"]["baseUrl"] == "http://127.0.0.1:3000"
        assert launched[0][1] == "dev"


def test_dashboard_supervisor_reuses_recent_starting_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    with TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir) / "runs"
        runs_dir.mkdir(parents=True)

        monkeypatch.setattr("tools.dashboard.serve._port_is_available", lambda host, port: False)
        launched: list[list[str]] = []

        def fake_launcher(command: list[str], cwd: Path, env: dict[str, str]) -> FakeProcess:
            launched.append(command)
            return FakeProcess(pid=6001)

        runtime_path = runs_dir / "_dashboard" / "runtime.json"
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.write_text(
            json.dumps(
                {
                    "updatedAt": time.time(),
                    "status": "starting",
                    "api": {"status": "starting", "baseUrl": "http://127.0.0.1:3000/api", "port": 3000},
                    "frontend": {
                        "status": "starting",
                        "host": "127.0.0.1",
                        "port": 3000,
                        "baseUrl": "http://127.0.0.1:3000",
                        "pid": 6001,
                        "command": ["pnpm.cmd", "dev"],
                    },
                }
            ),
            encoding="utf-8",
        )

        supervisor = DashboardSupervisor(
            runs_dir,
            launcher=fake_launcher,
            health_checker=lambda url: False,
        )
        runtime = supervisor.ensure_started(wait_for_health=False)

        assert runtime["status"] == "starting"
        assert launched == []


def test_dashboard_supervisor_falls_back_to_dev_when_preview_exits_early(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir) / "runs"
        repo_root = Path(temp_dir) / "repo"
        frontend_dir = repo_root / "apps" / "dashboard"
        runs_dir.mkdir()
        (frontend_dir / ".output").mkdir(parents=True)

        healthy_urls: set[str] = set()
        launched: list[list[str]] = []

        def fake_launcher(command: list[str], cwd: Path, env: dict[str, str]) -> FakeProcess:
            launched.append(command)
            if command[1] == "preview":
                return FakeExitedProcess(pid=4100, exit_code=1)
            port = int(command[command.index("--port") + 1])
            healthy_urls.add(f"http://127.0.0.1:{port}/api/health")
            return FakeProcess(pid=4200)

        monkeypatch.setattr(
            "tools.dashboard.serve._find_available_port",
            lambda host, preferred_port: 3000,
        )

        supervisor = DashboardSupervisor(
            runs_dir,
            repo_root=repo_root,
            launcher=fake_launcher,
            health_checker=lambda url: url in healthy_urls,
        )
        runtime = supervisor.ensure_started()

        assert launched[0][1] == "preview"
        assert launched[1][1] == "dev"
        assert runtime["frontend"]["command"][1] == "dev"
