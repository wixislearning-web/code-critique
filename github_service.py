import httpx
from typing import List, Dict, Optional
from fastapi import HTTPException
import os
import logging
from models import Repository, RepositoryData, RepositoryFile

logger = logging.getLogger(__name__)

class GitHubService:
    """GitHub API integration service"""
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://api.github.com"
    
    async def exchange_code_for_token(self, code: str) -> Dict[str, str]:
        """Exchange OAuth code for access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code
                },
                timeout=30.0
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to get access token")
            
            data = response.json()
            if "error" in data:
                raise HTTPException(status_code=400, detail=data.get("error_description", "OAuth error"))
            
            return data
    
    async def get_user_info(self, access_token: str) -> Dict:
        """Get GitHub user info"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                },
                timeout=30.0
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to get user info")
            
            return response.json()
    
    async def get_user_repositories(self, access_token: str) -> List[Repository]:
        """Get user repositories"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/user/repos",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                },
                params={
                    "sort": "updated",
                    "per_page": 100
                },
                timeout=30.0
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch repositories")
            
            repos_data = response.json()
            
            return [
                Repository(
                    id=repo["id"],
                    name=repo["name"],
                    full_name=repo["full_name"],
                    description=repo.get("description"),
                    html_url=repo["html_url"],
                    language=repo.get("language"),
                    updated_at=repo["updated_at"],
                    private=repo["private"],
                    stars=repo.get("stargazers_count", 0),
                    forks=repo.get("forks_count", 0)
                )
                for repo in repos_data
            ]
    
    async def get_repository_tree(self, access_token: str, repo_full_name: str) -> Dict:
        """Get repository file tree"""
        async with httpx.AsyncClient() as client:
            # Try main branch
            response = await client.get(
                f"{self.base_url}/repos/{repo_full_name}/git/trees/main",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                },
                params={"recursive": "1"},
                timeout=30.0
            )
            
            # Try master if main fails
            if response.status_code == 404:
                response = await client.get(
                    f"{self.base_url}/repos/{repo_full_name}/git/trees/master",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json"
                    },
                    params={"recursive": "1"},
                    timeout=30.0
                )
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch repository tree")
            
            return response.json()
    
    async def get_file_content(self, access_token: str, file_url: str) -> Optional[str]:
        """Get file content"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    file_url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3.raw"
                    },
                    timeout=30.0
                )
                return response.text if response.status_code == 200 else None
            except:
                return None
    
    def _is_code_file(self, file_path: str) -> bool:
        """Check if file is code"""
        code_extensions = {
            '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c', '.go',
            '.rb', '.php', '.html', '.css', '.scss', '.json', '.yaml', '.yml',
            '.md', '.sql', '.sh', '.rs', '.swift', '.kt', '.dart'
        }
        _, ext = os.path.splitext(file_path.lower())
        return ext in code_extensions
    
    def _should_skip_path(self, file_path: str) -> bool:
        """Check if path should be skipped"""
        skip = ['node_modules/', '.git/', '__pycache__/', 'venv/', 'dist/', 'build/']
        return any(pattern in file_path for pattern in skip)
    
    async def fetch_repository_contents(
        self,
        access_token: str,
        repo_full_name: str,
        max_files: int = 50
    ) -> RepositoryData:
        """Fetch repository contents"""
        tree_data = await self.get_repository_tree(access_token, repo_full_name)
        
        files: List[RepositoryFile] = []
        total_size = 0
        language_stats: Dict[str, int] = {}
        
        for item in tree_data.get("tree", []):
            if item["type"] != "blob" or len(files) >= max_files:
                continue
            
            file_path = item["path"]
            
            if not self._is_code_file(file_path) or self._should_skip_path(file_path):
                continue
            
            file_size = item.get("size", 0)
            if file_size > 50000:  # Skip large files
                continue
            
            content = await self.get_file_content(access_token, item["url"])
            
            if content:
                _, ext = os.path.splitext(file_path)
                language = self._detect_language(ext)
                
                files.append(RepositoryFile(
                    path=file_path,
                    content=content,
                    size=file_size,
                    language=language
                ))
                
                total_size += file_size
                if language:
                    language_stats[language] = language_stats.get(language, 0) + file_size
        
        primary_language = max(language_stats, key=language_stats.get) if language_stats else None
        
        return RepositoryData(
            repo_full_name=repo_full_name,
            files=files,
            file_count=len(files),
            total_size=total_size,
            primary_language=primary_language,
            languages=language_stats
        )
    
    def _detect_language(self, extension: str) -> Optional[str]:
        """Detect language from extension"""
        language_map = {
            '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
            '.java': 'Java', '.cpp': 'C++', '.c': 'C', '.go': 'Go',
            '.rb': 'Ruby', '.php': 'PHP', '.rs': 'Rust', '.swift': 'Swift',
            '.kt': 'Kotlin', '.dart': 'Dart', '.html': 'HTML', '.css': 'CSS'
        }
        return language_map.get(extension.lower())
