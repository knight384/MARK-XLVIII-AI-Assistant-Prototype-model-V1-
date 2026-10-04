import logging
from typing import List, Optional
from core.developer.project import ProjectAnalyzer

logger = logging.getLogger(__name__)

class BuildIntelligence:
    """Safe mechanisms for determining project commands."""
    
    def __init__(self, repo_path: str):
        self.analyzer = ProjectAnalyzer()
        self.repo_path = repo_path
        
    def detect_test_commands(self) -> List[str]:
        index = self.analyzer.analyze(self.repo_path)
        commands = []
        
        if "Python" in index.languages:
            commands.append("python -m pytest")
        if "TypeScript/JavaScript" in index.languages:
            if "npm" in index.package_managers:
                commands.append("npm test")
        if "Java" in index.languages:
            if "maven" in index.package_managers:
                commands.append("mvn test")
        if "Go" in index.languages:
            commands.append("go test ./...")
            
        if "Makefile" in index.build_configs:
            commands.append("make test")
            
        return commands

    def detect_build_commands(self) -> List[str]:
        index = self.analyzer.analyze(self.repo_path)
        commands = []
        
        if "TypeScript/JavaScript" in index.languages:
            if "npm" in index.package_managers:
                commands.append("npm run build")
        if "Java" in index.languages:
            if "maven" in index.package_managers:
                commands.append("mvn package")
        if "Go" in index.languages:
            commands.append("go build")
            
        if "Makefile" in index.build_configs:
            commands.append("make build")
            
        return commands
