"""Tests for DependencyExtractor — Python import resolution."""

from src.models.dependency import ConfidenceLabel, DependencyKind
from src.tools.dependency_extractor import DependencyExtractor


class TestPythonAbsoluteImport:
    def test_absolute_import(self):
        files = {
            "src/models/user.py": "class UserModel:\n    pass\n",
            "src/services/user_service.py": (
                "from src.models.user import UserModel\n"
                "\n"
                "class UserService:\n"
                "    pass\n"
            ),
        }
        graph = DependencyExtractor.extract_from_sources(files)
        edges = [
            e for e in graph.edges if e.source_file == "src/services/user_service.py"
        ]
        assert any(
            e.target_file == "src/models/user.py" and e.kind == DependencyKind.IMPORTS
            for e in edges
        )

    def test_multiple_imports(self):
        files = {
            "models.py": "class A:\n    pass\n",
            "utils.py": "def helper(): pass\n",
            "main.py": "from models import A\nfrom utils import helper\n",
        }
        graph = DependencyExtractor.extract_from_sources(files)
        targets = {e.target_file for e in graph.edges if e.source_file == "main.py"}
        assert "models.py" in targets
        assert "utils.py" in targets


class TestPythonRelativeImport:
    def test_relative_import(self):
        files = {
            "src/utils/helpers.py": "def helper(): pass\n",
            "src/utils/main.py": "from .helpers import helper\n",
        }
        graph = DependencyExtractor.extract_from_sources(files)
        assert any(
            e.source_file == "src/utils/main.py"
            and e.target_file == "src/utils/helpers.py"
            for e in graph.edges
        )

    def test_relative_import_confidence(self):
        files = {
            "pkg/a.py": "def foo(): pass\n",
            "pkg/b.py": "from .a import foo\n",
        }
        graph = DependencyExtractor.extract_from_sources(files)
        matching = [e for e in graph.edges if e.source_file == "pkg/b.py"]
        assert len(matching) >= 1
        assert matching[0].confidence in (
            ConfidenceLabel.EXTRACTED,
            ConfidenceLabel.INFERRED,
        )


class TestEdgeCases:
    def test_stdlib_import_skipped(self):
        files = {"main.py": "import os\nimport sys\nfrom pathlib import Path\n"}
        graph = DependencyExtractor.extract_from_sources(files)
        assert len(graph.edges) == 0

    def test_unresolvable_import_no_edge(self):
        files = {"main.py": "import nonexistent_package\n"}
        graph = DependencyExtractor.extract_from_sources(files)
        assert len(graph.edges) == 0

    def test_empty_files(self):
        graph = DependencyExtractor.extract_from_sources({})
        assert len(graph.edges) == 0
        assert graph.file_count == 0

    def test_file_count_set(self):
        files = {"a.py": "x = 1\n", "b.py": "y = 2\n", "c.py": "z = 3\n"}
        graph = DependencyExtractor.extract_from_sources(files)
        assert graph.file_count == 3

    def test_non_python_files_skipped(self):
        files = {
            "readme.md": "# Hello\n",
            "data.json": '{"key": "value"}\n',
            "main.py": "x = 1\n",
        }
        graph = DependencyExtractor.extract_from_sources(files)
        assert graph.file_count == 3
        assert len(graph.edges) == 0

    def test_import_plain_module(self):
        files = {
            "config.py": "DB_URL = 'sqlite:///db'\n",
            "app.py": "import config\n",
        }
        graph = DependencyExtractor.extract_from_sources(files)
        assert any(
            e.source_file == "app.py" and e.target_file == "config.py"
            for e in graph.edges
        )

    def test_self_import_skipped(self):
        files = {"a.py": "from a import something\n"}
        graph = DependencyExtractor.extract_from_sources(files)
        assert len(graph.edges) == 0
