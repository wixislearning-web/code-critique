from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)
security = HTTPBearer()

class AuthService:
    """Authentication and authorization service"""
    
    def __init__(self, jwt_secret: str, jwt_algorithm: str = "HS256"):
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
    
    def create_access_token(
        self,
        user_id: str,
        github_username: str,
        email: Optional[str] = None,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create JWT access token"""
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=7)
        
        payload = {
            "user_id": user_id,
            "github_username": github_username,
            "email": email,
            "exp": expire,
            "iat": datetime.utcnow()
        }
        
        try:
            token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
            return token
        except Exception as e:
            logger.error(f"Error creating JWT: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create access token"
            )
    
    def verify_token(self, token: str) -> Dict:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"}
            )
    
    async def get_current_user(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> Dict:
        """Get current authenticated user from token"""
        token = credentials.credentials
        payload = self.verify_token(token)
        
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )
        
        return {
            "user_id": user_id,
            "github_username": payload.get("github_username"),
            "email": payload.get("email")
        }
    
    def create_refresh_token(self, user_id: str) -> str:
        """Create refresh token"""
        expire = datetime.utcnow() + timedelta(days=30)
        
        payload = {
            "user_id": user_id,
            "type": "refresh",
            "exp": expire,
            "iat": datetime.utcnow()
        }
        
        try:
            token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
            return token
        except Exception as e:
            logger.error(f"Error creating refresh token: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create refresh token"
            )
    
    def verify_refresh_token(self, token: str) -> str:
        """Verify refresh token and return user_id"""
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm]
            )
            
            if payload.get("type") != "refresh":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type"
                )
            
            return payload.get("user_id")
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired"
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )