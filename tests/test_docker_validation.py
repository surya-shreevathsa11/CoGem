from __future__ import annotations

from cogem.docker_validation import (
    normalize_repo_kind_for_docker,
    plan_docker_dependency_install,
)


def test_normalize_repo_kind_for_docker() -> None:
    assert normalize_repo_kind_for_docker("node") == "node"
    assert normalize_repo_kind_for_docker("node-npm") == "node"
    assert normalize_repo_kind_for_docker("node-pnpm") == "node"
    assert normalize_repo_kind_for_docker("node-yarn") == "node"

    assert normalize_repo_kind_for_docker("python") == "python"
    assert normalize_repo_kind_for_docker("python-poetry") == "python"
    assert normalize_repo_kind_for_docker("python-pdm") == "python"


def test_plan_node_pnpm_frozen_lockfile() -> None:
    signals = {
        "package.json": True,
        "pnpm-lock.yaml": True,
    }
    plan = plan_docker_dependency_install("node-pnpm", signals)
    assert plan.image_family == "node"
    assert plan.commands == [
        ["corepack", "enable"],
        ["pnpm", "install", "--frozen-lockfile"],
    ]


def test_plan_node_pnpm_no_frozen_lockfile() -> None:
    signals = {
        "package.json": True,
        "pnpm-lock.yaml": False,
    }
    plan = plan_docker_dependency_install("node-pnpm", signals)
    assert plan.image_family == "node"
    assert plan.commands == [["corepack", "enable"], ["pnpm", "install"]]


def test_plan_node_yarn_frozen_lockfile() -> None:
    signals = {
        "package.json": True,
        "yarn.lock": True,
    }
    plan = plan_docker_dependency_install("node-yarn", signals)
    assert plan.image_family == "node"
    assert plan.commands == [
        ["corepack", "enable"],
        ["yarn", "install", "--frozen-lockfile"],
    ]


def test_plan_node_npm_prefers_ci_when_package_lock() -> None:
    signals = {
        "package-lock.json": True,
        "package.json": True,
    }
    plan = plan_docker_dependency_install("node-npm", signals)
    assert plan.image_family == "node"
    assert plan.commands == [["npm", "ci"]]


def test_plan_node_npm_falls_back_to_install() -> None:
    signals = {
        "package-lock.json": False,
        "package.json": True,
    }
    plan = plan_docker_dependency_install("node-npm", signals)
    assert plan.image_family == "node"
    assert plan.commands == [["npm", "install"]]


def test_plan_python_poetry() -> None:
    signals = {
        "pyproject.toml": True,
        "poetry.lock": True,
    }
    plan = plan_docker_dependency_install("python-poetry", signals)
    assert plan.image_family == "python"
    assert plan.commands == [
        ["pip", "install", "poetry"],
        ["poetry", "config", "virtualenvs.create", "false"],
        ["poetry", "install"],
    ]


def test_plan_python_pdm() -> None:
    signals = {
        "pyproject.toml": True,
        "pdm.lock": True,
    }
    plan = plan_docker_dependency_install("python-pdm", signals)
    assert plan.image_family == "python"
    assert plan.commands == [["pip", "install", "pdm"], ["pdm", "install"]]


def test_plan_python_requirements_txt() -> None:
    signals = {
        "requirements.txt": True,
        "pyproject.toml": False,
        "setup.py": False,
    }
    plan = plan_docker_dependency_install("python", signals)
    assert plan.image_family == "python"
    assert plan.commands == [["pip", "install", "-r", "requirements.txt"]]


def test_plan_python_pyproject_falls_back_to_install_dot() -> None:
    signals = {
        "requirements.txt": False,
        "pyproject.toml": True,
        "setup.py": False,
    }
    plan = plan_docker_dependency_install("python", signals)
    assert plan.image_family == "python"
    assert plan.commands == [["pip", "install", "."]]


def test_plan_unknown_kind_returns_empty() -> None:
    signals = {"package.json": True}
    plan = plan_docker_dependency_install("go", signals)
    assert plan.commands == []
    assert plan.image_family is None

