import httpx
from typing import List, Dict, Optional
from fastapi import HTTPException
import os
import logging
from models import Repository, RepositoryData, RepositoryFile

logger = logging.getLogger(__name__)

class GitHubService:
    """GitHub API integration service - Optimized for Smart Context"""
    
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

    def _is_code_file(self, file_path: str) -> bool:
        """Check if file is code and not a common dependency/config file"""
        code_exts = {
            '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.rb', '.php', 
            '.html', '.css', '.scss', '.sql', '.rs', '.dart', '.swift', '.kt', '.md', '.json', '.yml', '.yaml'
        }
        name, ext = os.path.splitext(file_path.lower())
        
        # Heuristics to skip less relevant files even if they have an extension
        if name.endswith(('_min', '.test', '.spec')) or ext in ('.lock', '.map', '.log'):
             return False
        
        return ext in code_exts
    
    def _should_skip_path(self, file_path: str) -> bool:
        """Check if path should be skipped (e.g., node_modules, build artifacts)"""
        skip = ['node_modules/', '.git/', '__pycache__/', 'venv/', 'dist/', 'build/', 'coverage/', 'package-lock.json', 'yarn.lock', '.idea/', '.vscode/']
        return any(pattern in file_path for pattern in skip)

    def _detect_language(self, extension: str) -> Optional[str]:
        """Detect language from extension"""
        mapping = {
            '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript', '.html': 'HTML',
            '.css': 'CSS', '.sql': 'SQL', '.java': 'Java', '.go': 'Go', '.rb': 'Ruby',
            '.php': 'PHP', '.rs': 'Rust', '.swift': 'Swift', '.kt': 'Kotlin', '.dart': 'Dart',
            '.md': 'Markdown', '.json': 'JSON', '.yml': 'YAML', '.yaml': 'YAML'
        }
        return mapping.get(extension.lower(), 'Other')

    async def fetch_repository_smart(self, access_token: str, repo_full_name: str) -> RepositoryData:
        """
        Smart Fetch: 
        1. Gets the file tree (for architecture context).
        2. Downloads content only for code files that are NOT large/binary (< 30KB).
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            
            # 1. Get Tree
            tree_urls = [
                f"{self.base_url}/repos/{repo_full_name}/git/trees/main?recursive=1",
                f"{self.base_url}/repos/{repo_full_name}/git/trees/master?recursive=1"
            ]
            
            res = None
            for url in tree_urls:
                res = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
                if res.status_code == 200:
                    break
            
            if not res or res.status_code != 200:
                raise HTTPException(status_code=404, detail="Repository tree not found on 'main' or 'master' branch.")
            
            tree_data = res.json().get("tree", [])
            
            files: List[RepositoryFile] = []
            total_size = 0
            language_stats: Dict[str, int] = {}
            MAX_FILE_SIZE_TO_FETCH = 30000 # 30 KB
            MAX_FILES_TO_FETCH = 70 
            
            # 2. Process Tree items
            for item in tree_data:
                path = item["path"]
                
                # Check file limits
                if len(files) >= MAX_FILES_TO_FETCH:
                    break
                
                # Skip non-code, irrelevant folders, or directories
                if item["type"] != "blob" or self._should_skip_path(path) or not self._is_code_file(path):
                    continue
                    
                size = item.get("size", 0)
                _, ext = os.path.splitext(path)
                language = self._detect_language(ext)
                
                repo_file = RepositoryFile(
                    path=path,
                    content="", # Default empty content
                    size=size,
                    language=language
                )
                
                # Only download content if it's small enough for the AI context window
                if size > 0 and size <= MAX_FILE_SIZE_TO_FETCH:
                    try:
                        # Use raw.githubusercontent.com for efficient content fetching
                        sha = res.json().get('sha', 'main')
                        raw_url = f"https://raw.githubusercontent.com/{repo_full_name}/{sha}/{path}"
                        
                        raw_res = await client.get(raw_url)
                        
                        if raw_res.status_code == 200:
                            repo_file.content = raw_res.text
                        else:
                            # Fallback to blob API if raw fails (though this is less common for code)
                            blob_res = await client.get(
                                item["url"], 
                                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3.raw"}
                            )
                            if blob_res.status_code == 200:
                                repo_file.content = blob_res.text

                    except Exception as e:
                        logger.warning(f"Failed to fetch content for {path}: {e}")
                
                files.append(repo_file)
                total_size += size
                if language:
                    language_stats[language] = language_stats.get(language, 0) + size

            primary_language = max(language_stats, key=language_stats.get) if language_stats else "Unknown"

            return RepositoryData(
                repo_full_name=repo_full_name,
                files=files,
                file_count=len(files),
                total_size=total_size,
                primary_language=primary_language,
                languages=language_stats
            )
