"""Tests for prerequisite-first / ordered intent detection."""

from cogem.task_intent import detect_prerequisite_first_task


def test_prerequisite_before_that_tell_me():
    t = (
        "i want you to build website for me but before that i need you to "
        "tell me how to connect to stich using mcp"
    )
    assert detect_prerequisite_first_task(t)


def test_prerequisite_first_explain():
    assert detect_prerequisite_first_task(
        "First explain how OAuth works, then we'll add login to the app"
    )


def test_pure_build_no_prerequisite():
    assert not detect_prerequisite_first_task("Build a landing page for my SaaS")


def test_build_first_not_prerequisite_info():
    """
    "First build the API" is implementation ordering, not "answer me first".
    """
    assert not detect_prerequisite_first_task("First build the API, then add the dashboard")

