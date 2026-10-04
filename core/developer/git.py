import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class GitIntelligence:
    """MARK-native Git capabilities for safe repository inspection."""
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        
    def _run_git(self, args: List[str]) -> str:
        """Run a bounded, read-only git command."""
        # Security: Do not allow arbitrary git execution here. 
        # Only structured predefined queries.
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                check=True,
                timeout=10 # Bounded execution
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error("Git command failed: %s", e.stderr)
            raise RuntimeError(f"Git error: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Git command timed out")

    def status(self) -> str:
        return self._run_git(["status", "--short"])
        
    def current_branch(self) -> str:
        return self._run_git(["branch", "--show-current"])
        
    def log(self, max_count: int = 10) -> str:
        return self._run_git(["log", "--oneline", f"-{max_count}"])
        
    def diff(self, cached: bool = False) -> str:
        # Bounded diff length to avoid blowing up context
        args = ["diff"]
        if cached:
            args.append("--cached")
        diff_output = self._run_git(args)
        if len(diff_output) > 20000:
            return diff_output[:20000] + "\n...[DIFF TRUNCATED]"
        return diff_output

    def diff_summary(self) -> str:
        return self._run_git(["diff", "--stat"])
        
    def show_commit(self, ref: str = "HEAD") -> str:
        return self._run_git(["show", ref, "--stat"])
