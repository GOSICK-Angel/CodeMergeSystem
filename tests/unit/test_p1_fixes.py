"""Unit tests for P1 fixes from the upstream-50-commits-v2 test report:

- O-B3: ``is_binary_asset`` routes binary files out of LLM batch review.
"""

from __future__ import annotations

from src.tools.binary_assets import BINARY_ASSET_EXTENSIONS, is_binary_asset


def test_is_binary_asset_common_extensions():
    assert is_binary_asset("tools/vanna/_assets/vanna_configure.png") is True
    assert is_binary_asset("models/icon.jpg") is True
    assert is_binary_asset("static/fonts/a.woff2") is True
    assert is_binary_asset("public/audio/bg.mp3") is True
    assert is_binary_asset("dist/plugin.zip") is True
    assert is_binary_asset("libs/mylib.so") is True
    assert is_binary_asset("vendor/tool.exe") is True


def test_is_binary_asset_case_insensitive():
    assert is_binary_asset("ICON.PNG") is True
    assert is_binary_asset("Track.Mp3") is True


def test_is_binary_asset_rejects_text_files():
    assert is_binary_asset("") is False
    assert is_binary_asset("src/app.py") is False
    assert is_binary_asset("README.md") is False
    assert is_binary_asset("config.yaml") is False
    assert is_binary_asset("style.css") is False
    assert is_binary_asset("index.html") is False
    assert is_binary_asset("data.json") is False
    assert is_binary_asset("locale.txt") is False


def test_is_binary_asset_svg_is_text():
    """SVG is XML/text — must stay in the LLM pipeline, not be filtered out."""
    assert is_binary_asset("assets/icon.svg") is False


def test_is_binary_asset_no_extension():
    assert is_binary_asset("Makefile") is False
    assert is_binary_asset("src/cli") is False


def test_binary_asset_extensions_set_is_not_empty():
    assert len(BINARY_ASSET_EXTENSIONS) > 20
    # All entries are lowercase and start with a dot.
    for ext in BINARY_ASSET_EXTENSIONS:
        assert ext.startswith(".")
        assert ext == ext.lower()
