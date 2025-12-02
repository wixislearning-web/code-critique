from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
from models import ReviewStatus

logger = logging.getLogger(__name__)

class DatabaseService:
    """Database service for Supabase operations"""
    
    def __init__(self, supabase_client):
        self.client = supabase_client
    
    # ============================================================================
    # USER OPERATIONS
    # ============================================================================
    
    async def get_all_users_count(self) -> int:
        """Get total user count (for health check)"""
        try:
            result = self.client.table("users").select("id", count="exact").execute()
            return result.count or 0
        except Exception as e:
            logger.error(f"Error getting user count: {e}")
            raise
    
    async def get_user_by_github_id(self, github_id: str) -> Optional[Dict]:
        """Get user by GitHub ID"""
        try:
            result = self.client.table("users").select("*").eq("github_id", github_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting user by GitHub ID: {e}")
            return None
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Get user by ID"""
        try:
            result = self.client.table("users").select("*").eq("id", user_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting user by ID: {e}")
            return None
    
    async def create_user(self, user_data: Dict) -> Dict:
        """Create new user"""
        try:
            result = self.client.table("users").insert(user_data).execute()
            return result.data[0]
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise
    
    async def update_github_token(self, user_id: str, access_token: str) -> None:
        """Update GitHub access token and last login"""
        try:
            self.client.table("users").update({
                "github_access_token": access_token,
                "last_login": datetime.utcnow().isoformat()
            }).eq("id", user_id).execute()
        except Exception as e:
            logger.error(f"Error updating GitHub token: {e}")
            raise
    
    async def get_user_github_token(self, user_id: str) -> Optional[str]:
        """Get user's GitHub access token"""
        try:
            result = self.client.table("users").select("github_access_token").eq("id", user_id).execute()
            return result.data[0]["github_access_token"] if result.data else None
        except Exception as e:
            logger.error(f"Error getting GitHub token: {e}")
            return None
    
    async def get_user_stats(self, user_id: str) -> Dict:
        """Get user statistics"""
        try:
            # Get all reviews
            reviews = await self.get_user_reviews(user_id)
            
            # Get subscription info
            subscription = await self.get_user_subscription(user_id)
            
            # Calculate stats
            total_reviews = len(reviews)
            completed_reviews = [r for r in reviews if r["status"] == ReviewStatus.COMPLETED]
            
            # Calculate average scores
            security_scores = [r.get("scores", {}).get("security", 0) for r in completed_reviews if r.get("scores")]
            quality_scores = [r.get("scores", {}).get("quality", 0) for r in completed_reviews if r.get("scores")]
            architecture_scores = [r.get("scores", {}).get("architecture", 0) for r in completed_reviews if r.get("scores")]
            
            avg_security = sum(security_scores) / len(security_scores) if security_scores else 0
            avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
            avg_architecture = sum(architecture_scores) / len(architecture_scores) if architecture_scores else 0
            
            # Reviews this month
            now = datetime.utcnow()
            reviews_this_month = subscription.get("reviews_used_this_month", 0) if subscription else 0
            reviews_limit = subscription.get("reviews_limit", 2) if subscription else 2
            reviews_remaining = max(0, reviews_limit - reviews_this_month)
            
            return {
                "total_reviews": total_reviews,
                "reviews_this_month": reviews_this_month,
                "reviews_remaining": reviews_remaining,
                "average_security_score": round(avg_security, 1),
                "average_quality_score": round(avg_quality, 1),
                "average_architecture_score": round(avg_architecture, 1),
                "improvement_trend": "stable"  # Could be calculated based on review history
            }
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {
                "total_reviews": 0,
                "reviews_this_month": 0,
                "reviews_remaining": 0,
                "average_security_score": 0,
                "average_quality_score": 0,
                "average_architecture_score": 0,
                "improvement_trend": "stable"
            }
    
    # ============================================================================
    # SUBSCRIPTION OPERATIONS
    # ============================================================================
    
    async def get_user_subscription(self, user_id: str) -> Optional[Dict]:
        """Get user subscription"""
        try:
            result = self.client.table("subscriptions").select("*").eq("user_id", user_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting subscription: {e}")
            return None
    
    async def create_subscription(self, subscription_data: Dict) -> Dict:
        """Create new subscription"""
        try:
            result = self.client.table("subscriptions").insert(subscription_data).execute()
            return result.data[0]
        except Exception as e:
            logger.error(f"Error creating subscription: {e}")
            raise
    
    async def check_review_limit(self, user_id: str) -> bool:
        """Check if user has reviews remaining"""
        try:
            subscription = await self.get_user_subscription(user_id)
            if not subscription:
                return False
            
            reviews_used = subscription.get("reviews_used_this_month", 0)
            reviews_limit = subscription.get("reviews_limit", 2)
            
            return reviews_used < reviews_limit
        except Exception as e:
            logger.error(f"Error checking review limit: {e}")
            return False
    
    async def increment_reviews_used(self, user_id: str) -> None:
        """Increment reviews used this month"""
        try:
            subscription = await self.get_user_subscription(user_id)
            if subscription:
                current_used = subscription.get("reviews_used_this_month", 0)
                self.client.table("subscriptions").update({
                    "reviews_used_this_month": current_used + 1
                }).eq("user_id", user_id).execute()
        except Exception as e:
            logger.error(f"Error incrementing reviews used: {e}")
    
    # ============================================================================
    # REVIEW OPERATIONS
    # ============================================================================
    
    async def create_review(self, review_data: Dict) -> Dict:
        """Create new review"""
        try:
            result = self.client.table("reviews").insert(review_data).execute()
            return result.data[0]
        except Exception as e:
            logger.error(f"Error creating review: {e}")
            raise
    
    async def get_review(self, review_id: str, user_id: str) -> Optional[Dict]:
        """Get review by ID"""
        try:
            result = self.client.table("reviews").select("*").eq("id", review_id).eq("user_id", user_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting review: {e}")
            return None
    
    async def get_user_reviews(self, user_id: str) -> List[Dict]:
        """Get all reviews for user"""
        try:
            result = self.client.table("reviews").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting user reviews: {e}")
            return []
    
    async def update_review_status(self, review_id: str, status: ReviewStatus) -> None:
        """Update review status"""
        try:
            self.client.table("reviews").update({
                "status": status.value
            }).eq("id", review_id).execute()
        except Exception as e:
            logger.error(f"Error updating review status: {e}")
    
    async def update_review_results(
        self,
        review_id: str,
        feedback: List[Dict],
        scores: Dict[str, int]
    ) -> None:
        """Update review with results"""
        try:
            self.client.table("reviews").update({
                "status": ReviewStatus.COMPLETED.value,
                "feedback": feedback,
                "scores": scores,
                "completed_at": datetime.utcnow().isoformat()
            }).eq("id", review_id).execute()
        except Exception as e:
            logger.error(f"Error updating review results: {e}")
    
    async def update_review_error(self, review_id: str, error_message: str) -> None:
        """Update review with error"""
        try:
            self.client.table("reviews").update({
                "status": ReviewStatus.FAILED.value,
                "error_message": error_message,
                "completed_at": datetime.utcnow().isoformat()
            }).eq("id", review_id).execute()
        except Exception as e:
            logger.error(f"Error updating review error: {e}")
    
    async def delete_review(self, review_id: str, user_id: str) -> bool:
        """Delete a review"""
        try:
            result = self.client.table("reviews").delete().eq("id", review_id).eq("user_id", user_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting review: {e}")
            return False
