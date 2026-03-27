from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class DockerInstallPlan:
    image_family: str | None
    commands: list[list[str]]


def normalize_repo_kind_for_docker(repo_kind: str) -> str:
    """
    Map detected repo kinds to Docker "families" used by the validator:
    - node-* => "node"
    - python-* => "python"
    """

    k = (repo_kind or "").strip()
    if k == "node" or k.startswith("node-"):
        return "node"
    if k == "python" or k.startswith("python-"):
        return "python"
    return k


def _has(signals: Mapping[str, bool], path: str) -> bool:
    return bool(signals.get(path))


def plan_docker_dependency_install(
    repo_kind: str, file_signals: Mapping[str, bool]
) -> DockerInstallPlan:
    """
    Plan best-effort dependency install commands inside the container.

    The caller is responsible for actually running these commands via Docker.
    """

    normalized = normalize_repo_kind_for_docker(repo_kind)
    commands: list[list[str]] = []

    if normalized == "node":
        if repo_kind == "node-npm" or repo_kind == "node":
            if _has(file_signals, "package-lock.json"):
                commands = [["npm", "ci"]]
            elif _has(file_signals, "package.json"):
                commands = [["npm", "install"]]
        elif repo_kind == "node-pnpm":
            if _has(file_signals, "package.json"):
                commands.append(["corepack", "enable"])
                if _has(file_signals, "pnpm-lock.yaml"):
                    commands.append(["pnpm", "install", "--frozen-lockfile"])
                else:
                    commands.append(["pnpm", "install"])
        elif repo_kind == "node-yarn":
            if _has(file_signals, "package.json"):
                commands.append(["corepack", "enable"])
                if _has(file_signals, "yarn.lock"):
                    commands.append(["yarn", "install", "--frozen-lockfile"])
                else:
                    commands.append(["yarn", "install"])
        else:
            commands = []

    elif normalized == "python":
        if repo_kind == "python":
            if _has(file_signals, "requirements.txt"):
                commands = [["pip", "install", "-r", "requirements.txt"]]
            elif _has(file_signals, "pyproject.toml") or _has(
                file_signals, "setup.py"
            ):
                commands = [["pip", "install", "."]]
        elif repo_kind == "python-poetry":
            if _has(file_signals, "poetry.lock"):
                commands = [
                    ["pip", "install", "poetry"],
                    ["poetry", "config", "virtualenvs.create", "false"],
                    ["poetry", "install"],
                ]
        elif repo_kind == "python-pdm":
                if _has(file_signals, "pdm.lock"):
                    commands = [["pip", "install", "pdm"], ["pdm", "install"]]
        else:
            commands = []
    else:
        commands = []

    if not commands:
        return DockerInstallPlan(image_family=normalized if normalized in ("node", "python") else None, commands=[])

    return DockerInstallPlan(image_family=normalized, commands=commands)

