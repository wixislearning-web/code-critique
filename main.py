from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Import our modules
from models import (
    GitHubOAuthRequest, GitHubOAuthResponse, Repository, ReviewRequest,
    Review, ReviewSummary, User, UserStats, HealthCheck, ReviewStatus
)
from database import DatabaseService
from github_service import GitHubService
from ai_service import AIService
from auth import AuthService

# Load environment variables
load_dotenv()

# Initialize FastAPI
app = FastAPI(
    title="CodeCritique API",
    description="AI-Powered Code Mentorship for Self-Taught Developers",
    version="1.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Services
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
JWT_SECRET = os.getenv("JWT_SECRET", "change-this-secret-key")

supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
db_service = DatabaseService(supabase_client)
github_service = GitHubService(GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET)
ai_service = AIService(ANTHROPIC_API_KEY)
auth_service = AuthService(JWT_SECRET)

# ============================================================================
# HEALTH & ROOT ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {
        "message": "CodeCritique API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health", response_model=HealthCheck)
async def health_check():
    # Check if services are available
    db_ok = True
    ai_ok = True
    
    try:
        await db_service.get_all_users_count()
    except:
        db_ok = False
    
    return HealthCheck(
        status="healthy" if (db_ok and ai_ok) else "degraded",
        timestamp=datetime.utcnow(),
        database_connected=db_ok,
        ai_service_available=ai_ok
    )

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.post("/auth/github/callback", response_model=GitHubOAuthResponse)
async def github_oauth_callback(request: GitHubOAuthRequest):
    """Handle GitHub OAuth callback"""
    
    # Exchange code for access token
    token_data = await github_service.exchange_code_for_token(request.code)
    github_access_token = token_data.get("access_token")
    
    if not github_access_token:
        raise HTTPException(status_code=400, detail="No access token received")
    
    # Get GitHub user info
    github_user = await github_service.get_user_info(github_access_token)
    
    github_id = str(github_user["id"])
    github_username = github_user["login"]
    email = github_user.get("email")
    avatar_url = github_user.get("avatar_url")
    
    # Check if user exists
    existing_user = await db_service.get_user_by_github_id(github_id)
    
    if existing_user:
        user_id = existing_user["id"]
        # Update token and last login
        await db_service.update_github_token(user_id, github_access_token)
    else:
        # Create new user
        user_data = {
            "github_id": github_id,
            "github_username": github_username,
            "github_access_token": github_access_token,
            "email": email,
            "avatar_url": avatar_url,
            "created_at": datetime.utcnow().isoformat(),
            "last_login": datetime.utcnow().isoformat()
        }
        new_user = await db_service.create_user(user_data)
        user_id = new_user["id"]
        
        # Create default subscription
        await db_service.create_subscription({
            "user_id": user_id,
            "tier": "free",
            "reviews_used_this_month": 0,
            "reviews_limit": 2,
            "subscription_start": datetime.utcnow().isoformat()
        })
    
    # Create JWT token
    jwt_token = auth_service.create_access_token(
        user_id=user_id,
        github_username=github_username,
        email=email
    )
    
    return GitHubOAuthResponse(
        access_token=jwt_token,
        user_id=user_id,
        github_username=github_username,
        avatar_url=avatar_url,
        email=email
    )

# ============================================================================
# USER ENDPOINTS
# ============================================================================

@app.get("/user/me", response_model=User)
async def get_current_user_info(current_user: dict = Depends(auth_service.get_current_user)):
    """Get current user information"""
    user_data = await db_service.get_user_by_id(current_user["user_id"])
    
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get review count
    reviews = await db_service.get_user_reviews(current_user["user_id"])
    user_data["reviews_count"] = len(reviews)
    user_data["subscription_tier"] = "free"  # Default
    
    return User(**user_data)

@app.get("/user/stats", response_model=UserStats)
async def get_user_stats(current_user: dict = Depends(auth_service.get_current_user)):
    """Get user statistics"""
    stats = await db_service.get_user_stats(current_user["user_id"])
    return UserStats(**stats)

# ============================================================================
# REPOSITORY ENDPOINTS
# ============================================================================

@app.get("/repositories", response_model=List[Repository])
async def get_repositories(current_user: dict = Depends(auth_service.get_current_user)):
    """Get user's GitHub repositories"""
    
    github_token = await db_service.get_user_github_token(current_user["user_id"])
    
    if not github_token:
        raise HTTPException(status_code=401, detail="GitHub token not found")
    
    repositories = await github_service.get_user_repositories(github_token)
    return repositories

# ============================================================================
# REVIEW ENDPOINTS
# ============================================================================

async def process_review_task(
    review_id: str,
    user_id: str,
    repo_full_name: str,
    focus_areas: List[str],
    context: str = None
):
    """Background task to process code review"""
    
    try:
        # Update status to processing
        await db_service.update_review_status(review_id, ReviewStatus.PROCESSING)
        
        # Get GitHub token
        github_token = await db_service.get_user_github_token(user_id)
        
        # Fetch repository contents
        repo_data = await github_service.fetch_repository_contents(
            github_token, 
            repo_full_name,
            max_files=50
        )
        
        # Analyze with AI
        feedback = await ai_service.analyze_repository(repo_data, focus_areas, context)
        
        # Calculate scores
        scores = ai_service.calculate_scores(feedback)
        
        # Update review with results
        await db_service.update_review_results(
            review_id,
            [f.dict() for f in feedback],
            scores
        )
        
        # Increment review count
        await db_service.increment_reviews_used(user_id)
        
    except Exception as e:
        print(f"Error processing review: {e}")
        await db_service.update_review_error(review_id, str(e))

@app.post("/reviews", response_model=Review, status_code=status.HTTP_201_CREATED)
async def create_review(
    request: ReviewRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(auth_service.get_current_user)
):
    """Create a new code review"""
    
    # Check if user has reviews remaining
    has_reviews = await db_service.check_review_limit(current_user["user_id"])
    
    if not has_reviews:
        raise HTTPException(
            status_code=403,
            detail="Review limit reached. Upgrade to Pro for unlimited reviews."
        )
    
    # Create review record
    review_data = {
        "user_id": current_user["user_id"],
        "repo_name": request.repo_full_name.split("/")[1],
        "repo_full_name": request.repo_full_name,
        "status": ReviewStatus.PENDING,
        "context": request.context,
        "focus_areas": request.focus_areas,
        "created_at": datetime.utcnow().isoformat()
    }
    
    review = await db_service.create_review(review_data)
    review_id = review["id"]
    
    # Start background processing
    background_tasks.add_task(
        process_review_task,
        review_id,
        current_user["user_id"],
        request.repo_full_name,
        request.focus_areas,
        request.context
    )
    
    return Review(**review)

@app.get("/reviews", response_model=List[ReviewSummary])
async def get_reviews(current_user: dict = Depends(auth_service.get_current_user)):
    """Get all reviews for current user"""
    
    reviews = await db_service.get_user_reviews(current_user["user_id"])
    
    summaries = []
    for review in reviews:
        feedback_count = len(review.get("feedback", [])) if review.get("feedback") else None
        summaries.append(ReviewSummary(
            id=review["id"],
            repo_name=review["repo_name"],
            repo_full_name=review["repo_full_name"],
            status=review["status"],
            scores=review.get("scores"),
            feedback_count=feedback_count,
            created_at=review["created_at"],
            completed_at=review.get("completed_at")
        ))
    
    return summaries

@app.get("/reviews/{review_id}", response_model=Review)
async def get_review(
    review_id: str,
    current_user: dict = Depends(auth_service.get_current_user)
):
    """Get a specific review"""
    
    review = await db_service.get_review(review_id, current_user["user_id"])
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    return Review(**review)

@app.delete("/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    review_id: str,
    current_user: dict = Depends(auth_service.get_current_user)
):
    """Delete a review"""
    
    review = await db_service.get_review(review_id, current_user["user_id"])
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # Delete from database (implement in database.py if needed)
    # For now, just return success
    return None

# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)