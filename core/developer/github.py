import logging
import requests
from typing import Dict, Any, List, Optional
from core.config import get_config_service

logger = logging.getLogger(__name__)

class GitHubIntelligence:
    """MARK-native GitHub integration.
    Adapted from jarvis-main/src/sites/github-manager.ts
    """
    
    def __init__(self, repo_full_name: str = ""):
        self.repo = repo_full_name
        self.base_url = "https://api.github.com"
        
    def _get_token(self) -> Optional[str]:
        return get_config_service().get_secret("github_token")
        
    def _get_headers(self) -> Dict[str, str]:
        token = self._get_token()
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "MARK-XLVIII-DeveloperAgent"
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            logger.warning("No GitHub token configured. Operating unauthenticated.")
        return headers

    def validate_token(self) -> Dict[str, Any]:
        """Validate stored token against GitHub API."""
        try:
            resp = requests.get(f"{self.base_url}/user", headers=self._get_headers(), timeout=15)
            if resp.ok:
                data = resp.json()
                scopes = [s.strip() for s in resp.headers.get("x-oauth-scopes", "").split(",") if s.strip()]
                return {"valid": True, "username": data.get("login"), "scopes": scopes}
            return {"valid": False, "username": None, "scopes": []}
        except Exception:
            return {"valid": False, "username": None, "scopes": []}
            
    def get_issue(self, issue_number: int) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/repos/{self.repo}/issues/{issue_number}", headers=self._get_headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()
        
    def get_pull_request(self, pr_number: int) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/repos/{self.repo}/pulls/{pr_number}", headers=self._get_headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()

    def list_issues(self, state: str = "open", max_results: int = 20) -> List[Dict[str, Any]]:
        resp = requests.get(f"{self.base_url}/repos/{self.repo}/issues?state={state}&per_page={max_results}", headers=self._get_headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()
        
    def create_repo(self, name: str, description: str = "", private: bool = True) -> Dict[str, Any]:
        """Create a new GitHub repository."""
        resp = requests.post(
            f"{self.base_url}/user/repos", 
            headers=self._get_headers(), 
            json={"name": name, "description": description, "private": private, "auto_init": False},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "owner": data.get("owner", {}).get("login"),
            "repo": data.get("name"),
            "cloneUrl": data.get("clone_url"),
            "htmlUrl": data.get("html_url")
        }

    def inject_token_into_remote(self, remote_url: str) -> str:
        """Inject token into HTTPS GitHub URL for non-interactive auth."""
        token = self._get_token()
        if not token:
            return remote_url
        if "://" in remote_url:
            parts = remote_url.split("://", 1)
            return f"{parts[0]}://{token}@{parts[1]}"
        return remote_url
