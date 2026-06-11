"""Project-local Claude Code install and reconcile for Co-Scientist."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


MANAGED_BLOCK_BEGIN = "<!-- CO_SCIENTIST:BEGIN -->"
MANAGED_BLOCK_END = "<!-- CO_SCIENTIST:END -->"
MANIFEST_VERSION = 1
SUPPORT_DIRECTORIES = ("shared-references",)
LEGACY_COMPAT_PATHS = (
    "tools/contracts/",
    "tools/mechanics/",
    "tools/artifacts/",
    "legacy/backend",
)


InstallAction = Literal["install", "reconcile", "uninstall"]
SourceKind = Literal["canonical-skill", "support", "entry-skill"]


@dataclass(frozen=True)
class ClaudeSkillSource:
    """One source directory that should become a Claude project skill entry."""

    name: str
    kind: SourceKind
    source_dir: Path


@dataclass(frozen=True)
class ClaudeInstallRecord:
    """One installed project skill entry."""

    name: str
    kind: SourceKind
    source_dir: str
    target_dir: str


@dataclass(frozen=True)
class ClaudeInstallResult:
    """Summary for one install/reconcile/uninstall run."""

    action: InstallAction
    project_root: str
    repo_root: str
    installed_skills: list[str]
    removed_skills: list[str]
    manifest_path: str
    claude_md_path: str


def _repo_root_from_module() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_project_root() -> Path:
    return _repo_root_from_module()


def _manifest_path(project_root: Path) -> Path:
    return project_root / ".co-scientist" / "installed-skills.json"


def _claude_skills_root(project_root: Path) -> Path:
    return project_root / ".claude" / "skills"


def _load_manifest(manifest_path: Path) -> dict[str, object] | None:
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def _copy_directory(source_dir: Path, target_dir: Path) -> None:
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists() or target_dir.is_symlink():
        _remove_path(target_dir)
    shutil.copytree(source_dir, target_dir)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _list_source_entries(repo_root: Path) -> list[ClaudeSkillSource]:
    canonical_root = repo_root / "skills"
    entry_root = repo_root / "skills" / "skills-claude-entry"
    if not canonical_root.is_dir():
        raise FileNotFoundError(f"Canonical skills directory not found: {canonical_root}")
    if not entry_root.is_dir():
        raise FileNotFoundError(f"Claude entry skills directory not found: {entry_root}")

    entries: list[ClaudeSkillSource] = []
    for child in sorted(canonical_root.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        if child.name in SUPPORT_DIRECTORIES:
            entries.append(ClaudeSkillSource(name=child.name, kind="support", source_dir=child))
            continue
        if (child / "SKILL.md").is_file():
            entries.append(ClaudeSkillSource(name=child.name, kind="canonical-skill", source_dir=child))

    entries.extend(
        ClaudeSkillSource(name=child.name, kind="entry-skill", source_dir=child)
        for child in sorted(entry_root.iterdir(), key=lambda item: item.name)
        if child.is_dir() and (child / "SKILL.md").is_file()
    )

    return entries


def collect_claude_skill_mirror_parity(*, project_root: Path, repo_root: Path) -> dict[str, object]:
    """Compare canonical skill sources against the installed Claude mirror."""
    project_root = project_root.resolve()
    repo_root = repo_root.resolve()
    claude_skills_root = _claude_skills_root(project_root)
    source_entries = _list_source_entries(repo_root)

    missing_files: list[str] = []
    mismatched_files: list[str] = []
    extra_files: list[str] = []
    checked_files = 0

    for entry in source_entries:
        target_dir = claude_skills_root / entry.name
        source_files = {path.relative_to(entry.source_dir) for path in entry.source_dir.rglob("*") if path.is_file()}
        target_files = (
            {path.relative_to(target_dir) for path in target_dir.rglob("*") if path.is_file()}
            if target_dir.is_dir()
            else set()
        )

        for relative_path in sorted(source_files):
            checked_files += 1
            source_path = entry.source_dir / relative_path
            target_path = target_dir / relative_path
            logical_path = f"{entry.name}/{relative_path.as_posix()}"
            if not target_path.is_file():
                missing_files.append(logical_path)
                continue
            if _sha256_file(source_path) != _sha256_file(target_path):
                mismatched_files.append(logical_path)

        extra_files.extend(
            f"{entry.name}/{relative_path.as_posix()}" for relative_path in sorted(target_files - source_files)
        )

    return {
        "checkedEntries": len(source_entries),
        "checkedFiles": checked_files,
        "missingFiles": missing_files,
        "mismatchedFiles": mismatched_files,
        "extraFiles": extra_files,
    }


def _render_managed_block() -> str:
    return "\n".join(
        [
            MANAGED_BLOCK_BEGIN,
            "## Managed Co-Scientist Project Skills",
            "",
            "Use the project-local Co-Scientist skills installed under `.claude/skills/`.",
            "",
            "Primary entry skills:",
            "",
            "- `/co-scientist-install`",
            "- `/co-scientist-doctor`",
            "- `/co-scientist-start`",
            "- `/co-scientist-params`",
            "- `/co-scientist-run <run-dir-or-config-path>`",
            "- `/co-scientist-resume <run-dir>`",
            "- `/co-scientist-validate <run-dir>`",
            "- `/co-scientist-dashboard <run-dir>`",
            "",
            "Execution rules:",
            "",
            "- Bootstrap fresh runs through `/co-scientist-start` and resumed runs through the matching "
            "project entry skills.",
            "- Use `/co-scientist-params` or `python -m tools.host.claude_project_cli params` when you "
            "need the high-level start controls before launch.",
            "- Run `python -m tools.host.claude_project_cli doctor` after install or reconcile when you "
            "need environment diagnostics.",
            "- Treat `budget` as per-round intensity, `iteration-policy` as semantic vs capped stopping, "
            "and `iteration-band` as a capped-run-only control.",
            "- Treat `human-checkpoint` as the pause policy. `completion_driven` plus "
            "`human-checkpoint=auto` should continue until a terminal stop signal instead of asking "
            "after every evolution round.",
            "- Fresh `start`, `run`, and `resume` calls attempt a background dashboard bootstrap and "
            "write run-local dashboard receipts.",
            "- Use `/co-scientist-dashboard <run-dir>` when you need the ready dashboard URL after "
            "background bootstrap.",
            "- Treat `runs/<run_id>/dashboard/LINKS.md` as the human-readable dashboard receipt and "
            "`runs/<run_id>/dashboard/LINKS.json` as the machine-readable receipt.",
            "- Treat `skills/` as the canonical workflow source.",
            "- Validate major writes through `python -m tools.validation.contract_validation`.",
            "- Treat `inspect_state` or `validation blocked` as an artifact-consistency stop that must "
            "be repaired before overview or resume.",
            "- Drive resume from `runs/<run_id>/state/PIPELINE_STATE.json` and `CURRENT_STAGE.json`.",
            "- Read execution semantics directly from `SKILL.md` plus canonical run artifacts.",
            "",
            "If the project skills are not installed yet, run one of:",
            "",
            "- `powershell -File tools/install/install_co_scientist.ps1`",
            "- `bash tools/install/install_co_scientist.sh`",
            MANAGED_BLOCK_END,
            "",
        ]
    )


def _render_claude_preamble() -> str:
    return "\n".join(
        [
            "# Co-Scientist for Claude Code",
            "",
            "This repository exposes a project-local Co-Scientist workflow for Claude Code.",
            "",
            "Canonical workflow and contract sources live in:",
            "",
            "- `skills/`",
            "- `skills/shared-references/`",
            "- `packages/agent_contracts/`",
            "- `tools/validation/contract_validation.py`",
            "- `runs/<run_id>/`",
            "",
            "The preamble above and the managed block below are maintained by `tools/install/claude_install.py`.",
            "Add any project-local notes after the managed block so reconcile can preserve them.",
            "",
        ]
    )


def _is_legacy_or_managed_claude_md(content: str) -> bool:
    if content.lstrip().startswith("# Co-Scientist for Claude Code"):
        return True
    if "Canonical workflow and contract sources live in:" in content:
        return True
    return any(path in content for path in LEGACY_COMPAT_PATHS)


def _ensure_claude_md(project_root: Path) -> Path:
    claude_md_path = project_root / "CLAUDE.md"
    base_body = _render_claude_preamble()
    managed_block = _render_managed_block()

    if claude_md_path.exists():
        content = claude_md_path.read_text(encoding="utf-8")
        if MANAGED_BLOCK_BEGIN in content and MANAGED_BLOCK_END in content:
            _prefix, remainder = content.split(MANAGED_BLOCK_BEGIN, maxsplit=1)
            _, suffix = remainder.split(MANAGED_BLOCK_END, maxsplit=1)
            content = base_body + managed_block + suffix.lstrip("\n")
        elif _is_legacy_or_managed_claude_md(content):
            content = base_body + managed_block
        else:
            content = content.rstrip() + "\n\n" + managed_block
    else:
        content = base_body + managed_block
    claude_md_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return claude_md_path


def install_claude_project(
    *,
    project_root: Path,
    repo_root: Path,
    action: InstallAction = "install",
) -> ClaudeInstallResult:
    """Install, reconcile, or uninstall Claude project skills for Co-Scientist."""
    project_root = project_root.resolve()
    repo_root = repo_root.resolve()
    manifest_path = _manifest_path(project_root)
    claude_skills_root = _claude_skills_root(project_root)
    claude_md_path = project_root / "CLAUDE.md"

    if action == "uninstall":
        manifest = _load_manifest(manifest_path)
        removed_skills: list[str] = []
        if manifest is not None:
            records = manifest.get("records", [])
            if isinstance(records, list):
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    target_dir_raw = record.get("target_dir")
                    name_raw = record.get("name")
                    if not isinstance(target_dir_raw, str) or not isinstance(name_raw, str):
                        continue
                    target_dir = Path(target_dir_raw)
                    _remove_path(target_dir)
                    removed_skills.append(name_raw)
        if manifest_path.exists():
            manifest_path.unlink()
        _ensure_claude_md(project_root)
        return ClaudeInstallResult(
            action="uninstall",
            project_root=str(project_root),
            repo_root=str(repo_root),
            installed_skills=[],
            removed_skills=removed_skills,
            manifest_path=str(manifest_path),
            claude_md_path=str(claude_md_path),
        )

    source_entries = _list_source_entries(repo_root)
    existing_manifest = _load_manifest(manifest_path)
    managed_names = {
        str(record.get("name"))
        for record in (existing_manifest or {}).get("records", [])
        if isinstance(record, dict) and isinstance(record.get("name"), str)
    }
    desired_names = {entry.name for entry in source_entries}

    if existing_manifest is not None:
        records = existing_manifest.get("records", [])
        if isinstance(records, list):
            for record in records:
                if not isinstance(record, dict):
                    continue
                name_raw = record.get("name")
                target_dir_raw = record.get("target_dir")
                if not isinstance(name_raw, str) or not isinstance(target_dir_raw, str):
                    continue
                if name_raw in desired_names:
                    continue
                _remove_path(Path(target_dir_raw))

    installed_records: list[ClaudeInstallRecord] = []
    for entry in source_entries:
        target_dir = claude_skills_root / entry.name
        if target_dir.exists() and entry.name not in managed_names:
            raise FileExistsError(
                f"Refusing to overwrite unmanaged Claude project skill path: {target_dir}. "
                "Remove it manually or uninstall the conflicting package first."
            )
        _copy_directory(entry.source_dir, target_dir)
        installed_records.append(
            ClaudeInstallRecord(
                name=entry.name,
                kind=entry.kind,
                source_dir=str(entry.source_dir),
                target_dir=str(target_dir),
            )
        )

    manifest_payload = {
        "version": MANIFEST_VERSION,
        "project_root": str(project_root),
        "repo_root": str(repo_root),
        "records": [asdict(record) for record in installed_records],
    }
    _write_json(manifest_path, manifest_payload)
    claude_md_path = _ensure_claude_md(project_root)

    return ClaudeInstallResult(
        action=action,
        project_root=str(project_root),
        repo_root=str(repo_root),
        installed_skills=[record.name for record in installed_records],
        removed_skills=[],
        manifest_path=str(manifest_path),
        claude_md_path=str(claude_md_path),
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Co-Scientist project skills for Claude Code.")
    parser.add_argument(
        "--project",
        type=Path,
        default=_default_project_root(),
        help="Target project root. Defaults to the current Co-Scientist repository root.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_repo_root_from_module(),
        help="Source Co-Scientist repository root. Defaults to the current repository.",
    )
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument("--reconcile", action="store_true", help="Refresh managed Claude project skills.")
    action_group.add_argument("--uninstall", action="store_true", help="Remove managed Claude project skills.")
    return parser.parse_args(argv)


def _resolve_action(args: argparse.Namespace) -> InstallAction:
    if args.uninstall:
        return "uninstall"
    if args.reconcile:
        return "reconcile"
    return "install"


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m tools.install.claude_install`."""
    args = _parse_args(argv)
    result = install_claude_project(
        project_root=args.project,
        repo_root=args.repo_root,
        action=_resolve_action(args),
    )
    print(json.dumps(asdict(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
