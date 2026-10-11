import sys


def test_project_uses_python_311() -> None:
    """Keep local checks aligned with the provisional baseline runtime."""
    assert sys.version_info[:2] == (3, 11)
