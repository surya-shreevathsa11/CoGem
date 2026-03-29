from pathlib import Path


def test_setup_py_is_thin_wrapper() -> None:
    content = Path("setup.py").read_text(encoding="utf-8")

    assert "setup()" in content
    assert "find_packages" not in content
    assert 'version="' not in content
    assert "install_requires" not in content


def test_pyproject_limits_setuptools_discovery_to_clogem() -> None:
    """Avoid multi-package flat-layout errors (e.g. stray `unused/` at repo root)."""
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.setuptools.packages.find]" in text
    assert 'include = ["clogem*"]' in text
    assert "unused*" in text
