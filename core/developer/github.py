import logging
import requests
from typing import Dict, Any, List, Optional
from core.config import get_config_service

logger = logging.getLogger(__name__)

class GitHubIntelligence:
    """MARK-native GitHub integration using adapter boundary."""
    
    def __init__(self, repo_full_name: str):
        self.repo = repo_full_name
        self.base_url = "https://api.github.com"
        
    def _get_headers(self) -> Dict[str, str]:
        token = get_config_service().get_secret("github_token")
        if not token:
            logger.warning("No GitHub token configured. Operating unauthenticated.")
            return {"Accept": "application/vnd.github.v3+json"}
        return {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
    def _get(self, endpoint: str) -> Dict[str, Any]:
        url = f"{self.base_url}/repos/{self.repo}/{endpoint}"
        resp = requests.get(url, headers=self._get_headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_issue(self, issue_number: int) -> Dict[str, Any]:
        return self._get(f"issues/{issue_number}")
        
    def get_pull_request(self, pr_number: int) -> Dict[str, Any]:
        return self._get(f"pulls/{pr_number}")
        
    def get_pr_diff(self, pr_number: int) -> str:
        url = f"{self.base_url}/repos/{self.repo}/pulls/{pr_number}"
        headers = self._get_headers()
        headers["Accept"] = "application/vnd.github.v3.diff"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.text[:20000] # Bounded

    def list_issues(self, state: str = "open", max_results: int = 20) -> List[Dict[str, Any]]:
        # This will list issues (and PRs since GitHub treats PRs as issues)
        url = f"{self.base_url}/repos/{self.repo}/issues?state={state}&per_page={max_results}"
        resp = requests.get(url, headers=self._get_headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()

    # NOTE: Write operations (mutations) MUST NOT be in this read-only adapter.
    # They are strictly mapped as tools bound to the PolicyEngine (see tools/developer_tools.py).
