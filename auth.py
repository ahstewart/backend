import jwt
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel import Session, select
from config import settings
from database import get_session
from schema import UserDB

# The Scheme (Looking for "Bearer <token>" header)
security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_session)
) -> UserDB:
    """
    Decodes the JWT, verifies it is signed by Supabase, 
    and returns the Database User object.
    """
    token = credentials.credentials

    try:
        # 1. Verify the Signature
        # Supabase uses HS256 and a secret key you get from their dashboard
        payload = jwt.decode(
            token, 
            settings.SUPABASE_JWT_SECRET, 
            algorithms=["HS256"],
            audience="authenticated"
        )
        
        user_uuid = payload.get("sub") # 'sub' is the User UUID in JWT standard
        email = payload.get("email")
        
        if not user_uuid:
            raise HTTPException(status_code=401, detail="Invalid Token: No User ID")

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token Expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid Token")

    # 2. Sync with our Database (The "Profile" Pattern)
    # The user exists in Supabase Auth, but maybe not in our 'users' table yet.
    # We check, and if missing, we create them (Lazy Registration).
    
    user = session.get(UserDB, user_uuid)
    
    if not user:
        # Auto-create the profile on first API call
        user = UserDB(
            id=user_uuid, # IMPORTANT: Match the Auth ID
            email=email,
            username=email.split("@")[0], # Temporary username
            is_developer=False
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    return user