import httpx
from typing import List, Dict
import json
import re
import logging
import os
from fastapi import HTTPException
from models import FeedbackItem, RepositoryData, Severity

logger = logging.getLogger(__name__)

# OpenRouter configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

class AIService:
    """
    AI Service with Hybrid Analysis (Static + LLM) using OpenRouter.
    1. Static Analysis (Regex/Stats) - Fast, Free, Deterministic
    2. LLM Analysis (OpenRouter) - Semantic, Explanatory, Architectural
    """
    
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": os.getenv("APP_URL", "http://localhost:8000"), # Recommended for OpenRouter usage
                "Content-Type": "application/json"
            }
        )
    
    async def analyze_repository(
        self,
        repo_data: RepositoryData,
        focus_areas: List[str],
        context: str = None
    ) -> List[FeedbackItem]:
        """Analyze repository using hybrid approach and OpenRouter API"""
        
        all_feedback = []
        
        # 1. Run Static Analysis (Free & Instant)
        static_feedback = self._run_static_analysis(repo_data)
        all_feedback.extend(static_feedback)
        
        # 2. Prepare Smart Context for AI
        static_summary = "\n".join([f"- Found {f.severity} issue in {f.file_path}: {f.title}" for f in static_feedback])
        
        # Create file tree for architectural context
        file_tree = "\n".join([f"{f.path} ({f.size} bytes, {f.language})" for f in repo_data.files])
        
        # Select critical snippets only (files that are small, or entry points, or flagged)
        relevant_snippets = self._get_smart_snippets(repo_data, static_feedback)
        
        focus_str = ", ".join(focus_areas).upper()
        
        prompt = f"""
You are a senior code mentor. Your goal is to review the architecture, quality, and security of the provided code structure and snippets.

**ANALYSIS FOCUS**: {focus_str}
Context: {context or "General Code Review"}
Repository: {repo_data.repo_full_name}

### PART 1: PROJECT STRUCTURE (File Tree)
Review this file tree for separation of concerns and maintainability.
{file_tree}

### PART 2: AUTOMATED FINDINGS (Static Analysis)
These issues were found by a static scanner. You must explain *why* they are significant and provide a clear suggestion.
{static_summary if static_summary else "No critical issues found by static scanner."}

### PART 3: KEY CODE SNIPPETS
Review these snippets for implementation quality, security vulnerabilities, and design patterns.
{relevant_snippets}

### INSTRUCTIONS
1. Explain WHY the automated findings matter (e.g., why is a monolithic file bad?).
2. Analyze the file tree for scalability issues (Is the folder structure effective? Are all services in `main.py` clean?).
3. Analyze the code snippets for poor practices like tight coupling or lack of typing (if applicable).
4. Do not repeat the static analysis title/description exactly; provide deeper context and mentorship.

Return ONLY a valid JSON array of objects.
Each object MUST have the following keys: 
`category` (security|quality|architecture), `severity` (critical|warning|info), `title`, `description`, `file_path`, `suggestion`, `reasoning`.
Ensure `file_path` is one of the paths from the file tree.
"""
        
        # 3. Call AI using OpenRouter
        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4000, 
                "temperature": 0.2,
                "response_format": {"type": "json_object"}
            }

            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()

            response_data = response.json()
            response_text = response_data['choices'][0]['message']['content']
            
            ai_feedback = self._parse_ai_response(response_text)
            all_feedback.extend(ai_feedback)
            
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter API error: {e.response.text}")
            raise HTTPException(status_code=502, detail=f"AI service failed (HTTP {e.response.status_code}): {e.response.text[:200]}")
        except Exception as e:
            logger.error(f"AI Analysis failed: {e}")
            raise HTTPException(status_code=500, detail=f"AI service failed: {e}")
        
        return all_feedback

    def _run_static_analysis(self, repo_data: RepositoryData) -> List[FeedbackItem]:
        """Detects secrets and monoliths using Regex/Math (No AI Cost)"""
        feedback = []
        
        # Regex for common secrets
        secret_patterns = {
            "Generic API Key": r"(?i)(api_key|apikey|secret|token|client_secret|auth_token)\s*=\s*['\"][a-zA-Z0-9_\-\.\/]{10,}['\"]",
            "Supabase Key": r"ey[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+",
            "Private Key Block": r"-----BEGIN (RSA|EC|PRIVATE) KEY-----"
        }
        
        for file in repo_data.files:
            if not file.content: continue
            
            # 1. Check for Monoliths (Architecture/Quality)
            line_count = len(file.content.splitlines())
            if line_count > 300: # Threshold for "Too Big"
                feedback.append(FeedbackItem(
                    category="architecture", severity=Severity.WARNING,
                    title="Large File/Monolithic Module Detected",
                    description=f"This file, `{file.path}`, has {line_count} lines. It may be a 'God Object' violating the Single Responsibility Principle (SRP).",
                    file_path=file.path,
                    suggestion="Split this file into smaller, focused modules (e.g., separate logic, models, and data access).",
                    reasoning="Large files are significantly harder to read, test, and maintain, increasing the risk of bugs."
                ))

            # 2. Check for Secrets (Security)
            for name, pattern in secret_patterns.items():
                if re.search(pattern, file.content):
                    # Exclude common JWT_SECRET placeholder
                    if "JWT_SECRET" in name and "change-this-secret-key" in file.content:
                        continue
                        
                    feedback.append(FeedbackItem(
                        category="security", severity=Severity.CRITICAL,
                        title=f"Potential Hardcoded Secret: {name}",
                        description=f"A pattern resembling a hardcoded secret ({name}) was found in `{file.path}`. The content should be redacted or moved to environment variables.",
                        file_path=file.path,
                        suggestion="Immediately move this value to environment variables (e.g., in the `.env` file) and load it using `os.getenv()`. Do not commit secrets to your repository.",
                        reasoning="Committing secrets directly to source control is a major security vulnerability that allows unauthorized access to your services."
                    ))

        return feedback

    def _get_smart_snippets(self, repo_data: RepositoryData, static_feedback: List[FeedbackItem]) -> str:
        """Selects only high-value code to send to AI to save tokens"""
        # 1. Always include 'entry points' and files that define core services
        entry_points = {'main.py', 'app.py', 'index.js', 'server.js', 'database.py', 'auth.py'}
        
        # 2. Include files that had static errors
        flagged_paths = {f.file_path for f in static_feedback}
        
        snippets = []
        token_count_est = 0
        MAX_TOKENS = 12000 # Keep context window manageable for cost/speed
        MAX_CONTENT_LENGTH = 1500 # Max characters per file
        
        for file in repo_data.files:
            is_entry = any(file.path.lower().endswith(ep) for ep in entry_points)
            is_flagged = file.path in flagged_paths
            
            # Send file if it's an entry point OR flagged, AND we haven't exceeded limit
            if (is_entry or is_flagged) and token_count_est < MAX_TOKENS:
                content = file.content[:MAX_CONTENT_LENGTH]
                snippets.append(f"\n--- File: {file.path} (Language: {file.language}) ---\n{content}\n")
                token_count_est += len(content) / 4 # Rough token math
                
        if not snippets:
            # Fallback to the first few small files if nothing was flagged
            for file in repo_data.files[:5]:
                if file.content and file.size < 10000:
                    content = file.content[:MAX_CONTENT_LENGTH]
                    snippets.append(f"\n--- File: {file.path} (Language: {file.language}) ---\n{content}\n")
                    token_count_est += len(content) / 4
        
        return "\n".join(snippets)

    def _parse_ai_response(self, text: str) -> List[FeedbackItem]:
        """Robust JSON parser that extracts JSON array from text"""
        try:
            # Find the JSON list in the response (sometimes AI adds text before/after)
            match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                
                feedback_list = []
                for item in data:
                    try:
                        feedback_list.append(FeedbackItem(**item))
                    except Exception as ve:
                        logger.warning(f"Failed to validate feedback item: {ve} - Data: {item.get('title')}")
                        continue
                return feedback_list
        except Exception as e:
            logger.error(f"Failed to parse AI JSON: {e} | Text: {text[:500]}")
        return []

    def calculate_scores(self, feedback: List[FeedbackItem]) -> Dict[str, int]:
        """Calculate scores from feedback"""
        scores = {"security": 10, "quality": 10, "architecture": 10}
        
        for item in feedback:
            category = item.category
            severity = item.severity
            
            deduction = {"critical": 4, "warning": 2, "info": 1}.get(severity.lower(), 1)
            
            if category in scores:
                scores[category] = max(0, scores[category] - deduction)
        
        scores["overall"] = round(sum(scores.values()) / 3)
        
        return scores
