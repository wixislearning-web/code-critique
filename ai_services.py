import anthropic
from typing import List, Dict
import json
import re
import logging
from models import FeedbackItem, RepositoryData, FeedbackCategory, Severity

logger = logging.getLogger(__name__)

class AIService:
    """AI-powered code analysis service"""
    
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
    
    async def analyze_repository(
        self,
        repo_data: RepositoryData,
        focus_areas: List[str],
        context: str = None
    ) -> List[FeedbackItem]:
        """Analyze repository and return feedback"""
        
        all_feedback = []
        
        file_summaries = self._create_file_summaries(repo_data)
        code_samples = self._create_code_samples(repo_data)
        
        if "security" in focus_areas:
            security_feedback = await self._analyze_security(repo_data, file_summaries, code_samples, context)
            all_feedback.extend(security_feedback)
        
        if "quality" in focus_areas:
            quality_feedback = await self._analyze_quality(repo_data, file_summaries, code_samples, context)
            all_feedback.extend(quality_feedback)
        
        if "architecture" in focus_areas:
            architecture_feedback = await self._analyze_architecture(repo_data, file_summaries, code_samples, context)
            all_feedback.extend(architecture_feedback)
        
        return all_feedback
    
    def _create_file_summaries(self, repo_data: RepositoryData) -> str:
        """Create file structure summary"""
        summaries = [
            f"- {file.path} ({file.size} bytes, {file.language or 'Unknown'})"
            for file in repo_data.files
        ]
        return "\n".join(summaries)
    
    def _create_code_samples(self, repo_data: RepositoryData, max_files: int = 15) -> str:
        """Create code samples for AI"""
        samples = []
        for file in repo_data.files[:max_files]:
            content = file.content[:3000] if len(file.content) > 3000 else file.content
            samples.append(f"\n### File: {file.path}\n```{file.language or ''}\n{content}\n```")
        return "\n".join(samples)
    
    async def _analyze_security(self, repo_data, file_summaries, code_samples, context) -> List[FeedbackItem]:
        """Analyze security vulnerabilities"""
        
        prompt = f"""You are a senior security engineer reviewing code for CodeCritique.

Repository: {repo_data.repo_full_name}
Primary Language: {repo_data.primary_language or 'Multiple'}
{f'Context: {context}' if context else ''}

File Structure:
{file_summaries}

Code Samples:
{code_samples}

Identify 3-5 security issues focusing on:
- Hardcoded secrets
- SQL injection
- XSS vulnerabilities
- Authentication issues
- Data exposure

Return ONLY valid JSON array:
[
  {{
    "category": "security",
    "severity": "critical" | "warning" | "info",
    "title": "Brief title",
    "description": "What the issue is",
    "file_path": "path/to/file.py" or null,
    "line_number": 42 or null,
    "code_snippet": "code" or null,
    "suggestion": "How to fix",
    "reasoning": "Why this matters"
  }}
]"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text
            return self._parse_ai_response(response_text, "security")
        except Exception as e:
            logger.error(f"Security analysis error: {e}")
            return []
    
    async def _analyze_quality(self, repo_data, file_summaries, code_samples, context) -> List[FeedbackItem]:
        """Analyze code quality"""
        
        prompt = f"""You are a senior software engineer reviewing code quality.

Repository: {repo_data.repo_full_name}
Primary Language: {repo_data.primary_language or 'Multiple'}

File Structure:
{file_summaries}

Code Samples:
{code_samples}

Identify 3-5 code quality issues:
- Naming conventions
- DRY violations
- Error handling
- Code readability
- Best practices

Return ONLY valid JSON array with category "quality"."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text
            return self._parse_ai_response(response_text, "quality")
        except Exception as e:
            logger.error(f"Quality analysis error: {e}")
            return []
    
    async def _analyze_architecture(self, repo_data, file_summaries, code_samples, context) -> List[FeedbackItem]:
        """Analyze architecture"""
        
        prompt = f"""You are a software architect reviewing project structure.

Repository: {repo_data.repo_full_name}

File Structure:
{file_summaries}

Code Samples:
{code_samples}

Provide 2-4 architectural insights:
- Project organization
- Separation of concerns
- Scalability
- Design patterns

Return ONLY valid JSON array with category "architecture"."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text
            return self._parse_ai_response(response_text, "architecture")
        except Exception as e:
            logger.error(f"Architecture analysis error: {e}")
            return []
    
    def _parse_ai_response(self, response_text: str, expected_category: str) -> List[FeedbackItem]:
        """Parse AI JSON response"""
        try:
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if not json_match:
                return []
            
            json_text = json_match.group()
            feedback_data = json.loads(json_text)
            
            feedback_items = []
            for item in feedback_data:
                try:
                    item["category"] = expected_category
                    feedback_items.append(FeedbackItem(**item))
                except:
                    continue
            
            return feedback_items
        except:
            return []
    
    def calculate_scores(self, feedback: List[FeedbackItem]) -> Dict[str, int]:
        """Calculate scores from feedback"""
        scores = {"security": 10, "quality": 10, "architecture": 10}
        
        for item in feedback:
            category = item.category
            severity = item.severity
            
            deduction = {"critical": 3, "warning": 2, "info": 1}.get(severity, 1)
            
            if category in scores:
                scores[category] = max(0, scores[category] - deduction)
        
        scores["overall"] = round(sum(scores.values()) / 3)
        
        return scores