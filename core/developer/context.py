import os
from pathlib import Path
from typing import List, Optional
from core.developer.project import ProjectAnalyzer, ProjectIndex
from core.developer.git import GitIntelligence

class ContextBuilder:
    """Constructs bounded, developer-specific context assemblies."""
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.analyzer = ProjectAnalyzer()
        try:
            self.git = GitIntelligence(repo_path)
        except Exception:
            self.git = None
            
    def build_context(self, task_goal: str, relevant_files: Optional[List[str]] = None) -> str:
        index = self.analyzer.analyze(str(self.repo_path))
        
        context_parts = []
        context_parts.append(f"PROJECT CONTEXT:\nRoot: {index.root_path}")
        context_parts.append(f"Languages: {', '.join(index.languages)}")
        context_parts.append(f"Source Dirs: {', '.join(index.source_directories)}")
        context_parts.append(f"Test Dirs: {', '.join(index.test_directories)}")
        
        if self.git:
            try:
                context_parts.append(f"\nGIT STATE:\nBranch: {self.git.current_branch()}")
                status = self.git.status()
                if status:
                    context_parts.append(f"Pending Changes:\n{status}")
            except Exception:
                pass
                
        # Attach bounded file contents
        if relevant_files:
            context_parts.append("\nRELEVANT FILES:")
            for rel_file in relevant_files[:5]: # Bounded strictly to 5 files
                file_path = self.repo_path / rel_file
                if file_path.is_file():
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        # Bound individual file sizes
                        if len(content) > 15000:
                            content = content[:15000] + "\n...[TRUNCATED]"
                        context_parts.append(f"--- {rel_file} ---\n{content}\n")
                    except Exception as e:
                        context_parts.append(f"--- {rel_file} ---\nError reading file: {e}\n")
        
        return "\n".join(context_parts)
