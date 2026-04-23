"""Detect binary asset files so AUTO_MERGE can bypass LLM batch processing
for them (O-B3).

Text-oriented LLM pipelines crash or waste cost when fed PNG/woff/zip
content. These helpers give a cheap, extension-based decision so
``auto_merge`` can route binary files straight to ``take_target`` (or
``escalate_human`` for the both-modified case) without ever touching the
batch file-review prompts.
"""

from __future__ import annotations

from pathlib import PurePosixPath

# Extensions that indicate binary / non-human-readable assets.
# Keep lowercase; comparisons use ``.lower()``.
BINARY_ASSET_EXTENSIONS: frozenset[str] = frozenset(
    {
        # Images
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".icns",
        ".webp",
        ".tif",
        ".tiff",
        ".psd",
        ".ai",
        ".eps",
        ".heic",
        ".avif",
        # Fonts
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        # Audio / video
        ".mp3",
        ".wav",
        ".flac",
        ".ogg",
        ".aac",
        ".m4a",
        ".mp4",
        ".m4v",
        ".mov",
        ".avi",
        ".webm",
        ".mkv",
        ".wmv",
        # Archives / blobs
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".whl",
        ".jar",
        ".war",
        ".apk",
        ".ipa",
        # Compiled / native
        ".so",
        ".dll",
        ".dylib",
        ".exe",
        ".bin",
        ".class",
        ".pyc",
        ".pyo",
        ".o",
        ".a",
        # Documents that are effectively binary
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".odt",
        ".ods",
        ".odp",
        # Data blobs
        ".db",
        ".sqlite",
        ".sqlite3",
        ".bak",
        # ML / scientific
        ".safetensors",
        ".ckpt",
        ".pt",
        ".onnx",
        ".npz",
        ".npy",
    }
)


def is_binary_asset(file_path: str) -> bool:
    """Return True if ``file_path`` looks like a binary asset by extension.

    Notes
    -----
    - ``.svg`` is intentionally NOT treated as binary — SVGs are XML and
      LLM review over them sometimes adds value (diff is readable).
    - Case-insensitive on the extension.
    """

    if not file_path:
        return False
    suffix = PurePosixPath(file_path).suffix.lower()
    return suffix in BINARY_ASSET_EXTENSIONS
