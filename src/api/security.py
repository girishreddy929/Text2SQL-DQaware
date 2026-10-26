# src/api/security.py
import os
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# We use a simple Bearer token for API security
security = HTTPBearer()

# In production, this should be a strong secret in the .env file.
# For local development, we provide a default fallback.
API_KEY = os.getenv("TRUSTSQL_API_KEY", "trustsql-secret-key")


def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    """Validates the Bearer token sent in the Authorization header."""
    if credentials.credentials != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )
    return credentials.credentials
