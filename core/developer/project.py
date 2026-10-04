import os
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Set, Dict

@dataclass
class ProjectIndex:
    root_path: str
    git_root: Optional[str]
    languages: List[str]
    package_managers: List[str]
    source_directories: List[str]
    test_directories: List[str]
    build_configs: List[str]

class ProjectAnalyzer:
    """Lightweight repository intelligence abstraction."""
    
    IGNORE_DIRS = {".git", "node_modules", "venv", "__pycache__", "dist", "build", ".pytest_cache", ".idea", ".vscode"}
    
    def analyze(self, path: str) -> ProjectIndex:
        root = Path(path).resolve()
        
        # 1. Git root
        git_root = self._find_git_root(root)
        
        languages = set()
        package_managers = set()
        src_dirs = []
        test_dirs = []
        build_configs = []
        
        # Top level scan for manifests
        for item in root.iterdir():
            if item.is_file():
                name = item.name
                if name == "package.json":
                    package_managers.add("npm")
                    languages.add("TypeScript/JavaScript")
                elif name == "requirements.txt" or name == "pyproject.toml" or name == "setup.py":
                    package_managers.add("pip")
                    languages.add("Python")
                elif name == "pom.xml":
                    package_managers.add("maven")
                    languages.add("Java")
                elif name == "go.mod":
                    package_managers.add("go mod")
                    languages.add("Go")
                elif name in ["Makefile", "CMakeLists.txt", "build.gradle", "docker-compose.yml"]:
                    build_configs.append(name)
            elif item.is_dir() and item.name not in self.IGNORE_DIRS:
                name_lower = item.name.lower()
                if name_lower in ["src", "source", "app", "lib", "core"]:
                    src_dirs.append(item.name)
                elif name_lower in ["tests", "test", "spec", "specs"]:
                    test_dirs.append(item.name)
                    
        return ProjectIndex(
            root_path=str(root),
            git_root=str(git_root) if git_root else None,
            languages=list(languages),
            package_managers=list(package_managers),
            source_directories=src_dirs,
            test_directories=test_dirs,
            build_configs=build_configs
        )

    def _find_git_root(self, current: Path) -> Optional[Path]:
        while current != current.parent:
            if (current / ".git").is_dir():
                return current
            current = current.parent
        return None
