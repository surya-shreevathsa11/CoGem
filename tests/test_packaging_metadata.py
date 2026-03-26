from pathlib import Path


def test_setup_py_is_thin_wrapper() -> None:
    content = Path("setup.py").read_text(encoding="utf-8")

    assert "setup()" in content
    assert "find_packages" not in content
    assert 'version="' not in content
    assert "install_requires" not in content
