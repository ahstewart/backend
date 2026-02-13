import os
import requests
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlmodel import Session
from database import get_session
from schema import UserDB

# ==========================================
# CONFIG
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "http://127.0.0.1:54321")
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"

# We support both just in case your config flips back
ALGORITHMS = ["HS256", "RS256", "ES256"] 

security = HTTPBearer()

# ==========================================
# HELPER: FETCH PUBLIC KEYS
# ==========================================
def get_public_key(token: str) -> Optional[Dict[str, Any]]:
    """
    Downloads the Public Key (JWK) from Supabase that matches the token's 'kid'.
    """
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        
        if not kid:
            return None # If no 'kid', it might be an HS256 token (Symmetric)

        # In production, you should cache this request!
        jwks = requests.get(JWKS_URL).json()
        
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return key
    except Exception as e:
        print(f"[AUTH ERROR] Could not fetch JWKS: {e}")
    return None

# ==========================================
# THE BOUNCER
# ==========================================
async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security), 
    session: Session = Depends(get_session)
) -> UserDB:
    
    token = creds.credentials
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 1. Try to find a Public Key (ES256 / RS256)
        key = get_public_key(token)
        
        if key:
            # Case A: Asymmetric (ES256) -> Verify with Public Key
            payload = jwt.decode(
                token, 
                key, # Pass the JWK dict directly
                algorithms=ALGORITHMS, 
                audience="authenticated"
            )
        else:
            # Case B: Symmetric (HS256) -> Verify with Secret String
            secret = os.getenv("SUPABASE_JWT_SECRET")
            payload = jwt.decode(
                token, 
                secret, 
                algorithms=ALGORITHMS, 
                audience="authenticated"
            )

        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        
        if user_id is None:
            raise credentials_exception
            
    except JWTError as e:
        print(f"[AUTH ERROR] Token verification failed: {e}")
        raise credentials_exception

    # 2. Database Lookup
    user = session.get(UserDB, user_id)

    if not user:
        user = UserDB(
            id=user_id,
            email=email,
            username=email.split("@")[0] if email else "unknown",
            is_developer=False,
            created_at=payload.get("created_at")
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    return user