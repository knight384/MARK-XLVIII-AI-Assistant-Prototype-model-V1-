import subprocess
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

class GitIntelligence:
    """MARK-native Git capabilities for safe repository inspection and mutation.
    Adapted from jarvis-main/src/sites/git-manager.ts
    """
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        
    def _run_git(self, args: List[str], check: bool = True) -> str:
        """Run a git command in the repository."""
        env = None # Equivalent to GIT_TERMINAL_PROMPT=0 in TS, but skipping for basic env
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                check=check,
                timeout=15
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error("Git command failed: %s", e.stderr)
            raise RuntimeError(f"git {args[0]} failed: {e.stderr.strip() or e.stdout.strip()}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Git command timed out")

    def status(self) -> str:
        return self._run_git(["status", "--short"])
        
    def current_branch(self) -> str:
        return self._run_git(["branch", "--show-current"])
        
    def log(self, max_count: int = 50) -> List[Dict[str, Any]]:
        try:
            out = self._run_git(["log", f"--max-count={max_count}", "--format=%H|%h|%s|%an|%at"])
            if not out:
                return []
            commits = []
            for line in out.splitlines():
                parts = line.split("|")
                if len(parts) == 5:
                    commits.append({
                        "hash": parts[0],
                        "shortHash": parts[1],
                        "message": parts[2],
                        "author": parts[3],
                        "date": int(parts[4]) * 1000
                    })
            return commits
        except Exception:
            return []
        
    def diff(self, cached: bool = False) -> str:
        args = ["diff"]
        if cached:
            args.append("--cached")
        return self._run_git(args)

    def is_dirty(self) -> bool:
        return len(self._run_git(["status", "--porcelain"])) > 0

    def merge(self, branch: str) -> Dict[str, Any]:
        try:
            self._run_git(["merge", branch])
            return {"success": True}
        except RuntimeError as e:
            # Check for conflicts
            status = self._run_git(["status", "--porcelain"])
            conflicts = [line[3:].strip() for line in status.splitlines() if line.startswith("UU ") or line.startswith("AA ")]
            if conflicts:
                return {"success": False, "conflicts": conflicts}
            
            # Abort merge if failed for other reasons
            try:
                self._run_git(["merge", "--abort"], check=False)
            except Exception:
                pass
            raise e

    def push(self, remote_url: str, branch: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        target_branch = branch or self.current_branch()
        args = ["push", "-u", remote_url, target_branch]
        if force:
            args.insert(1, "--force")
        try:
            self._run_git(args)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def pull(self, remote_url: str, branch: Optional[str] = None) -> Dict[str, Any]:
        target_branch = branch or self.current_branch()
        try:
            self._run_git(["pull", remote_url, target_branch])
            return {"success": True}
        except RuntimeError as e:
            # Check conflicts
            status = self._run_git(["status", "--porcelain"], check=False)
            conflicts = [line[3:].strip() for line in status.splitlines() if line.startswith("UU ") or line.startswith("AA ")]
            if conflicts:
                return {"success": False, "conflicts": conflicts}
            return {"success": False, "error": str(e)}

    def get_remote_status(self, remote_url: str) -> Dict[str, Any]:
        match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", remote_url)
        owner, repo = match.groups() if match else (None, None)
        
        try:
            self._run_git(["fetch", remote_url, "--quiet"], check=False)
        except Exception:
            pass
            
        current = self.current_branch()
        ahead = behind = 0
        
        try:
            behind_str = self._run_git(["rev-list", "--count", f"HEAD..origin/{current}"])
            behind = int(behind_str) if behind_str else 0
        except Exception:
            pass
            
        try:
            ahead_str = self._run_git(["rev-list", "--count", f"origin/{current}..HEAD"])
            ahead = int(ahead_str) if ahead_str else 0
        except Exception:
            try:
                total_str = self._run_git(["rev-list", "--count", "HEAD"])
                ahead = int(total_str) if total_str else 0
            except Exception:
                pass
                
        return {
            "hasRemote": True,
            "remoteUrl": remote_url,
            "owner": owner,
            "repo": repo,
            "ahead": ahead,
            "behind": behind
        }
