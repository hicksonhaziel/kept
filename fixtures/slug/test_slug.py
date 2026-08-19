import pytest

from slug import slugify


@pytest.mark.verifies("REQ-1.1")
def test_lowercases():
    assert slugify("Hello World") == "hello-world"


@pytest.mark.verifies("REQ-1.2")
def test_collapses_spaces():
    assert slugify("a    b") == "a-b"


@pytest.mark.verifies("REQ-1.3")
def test_strips_punctuation():
    assert slugify("Hello, World!") == "hello-world"


@pytest.mark.verifies("REQ-1.4")
def test_no_edge_hyphens():
    # Deliberately weak: only checks the ends, not the content.
    result = slugify("  spaced  ")
    assert not result.startswith("-")
    assert not result.endswith("-")


@pytest.mark.verifies("REQ-1.5")
def test_empty():
    assert slugify("") == ""
