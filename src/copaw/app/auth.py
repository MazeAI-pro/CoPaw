# -*- coding: utf-8 -*-
"""Authentication module for CoPaw console."""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwk, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from copaw.constant import WORKING_DIR
from .user_scope import DEFAULT_USER_ID, normalize_user_id

logger = logging.getLogger(__name__)

# Default credentials (hardcoded, can be overridden via env vars)
DEFAULT_USERNAME = "copaw_admin"
DEFAULT_PASSWORD = "Xk9#mP2$vL7@nQ4wR8tY"

# JWKS cache for Supabase ES256 key verification
_jwks_cache: dict[str, Any] = {"keys": None, "expires_at": 0}


@dataclass
class AuthConfig:
    """Authentication configuration."""

    enabled: bool = True
    username: str = DEFAULT_USERNAME
    password: str = DEFAULT_PASSWORD
    session_expire_hours: int = 24
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""

    def __post_init__(self) -> None:
        """Load configuration from environment variables."""
        env_enabled = os.environ.get("COPAW_AUTH_ENABLED", "").lower()
        if env_enabled in ("false", "0", "no"):
            self.enabled = False
        elif env_enabled in ("true", "1", "yes"):
            self.enabled = True

        env_username = os.environ.get("COPAW_AUTH_USERNAME")
        if env_username:
            self.username = env_username

        env_password = os.environ.get("COPAW_AUTH_PASSWORD")
        if env_password:
            self.password = env_password

        env_expire = os.environ.get("COPAW_AUTH_SESSION_EXPIRE_HOURS")
        if env_expire and env_expire.isdigit():
            self.session_expire_hours = int(env_expire)

        self.supabase_url = os.environ.get("COPAW_SUPABASE_URL", "").strip()
        self.supabase_anon_key = os.environ.get("COPAW_SUPABASE_ANON_KEY", "").strip()
        self.supabase_jwt_secret = os.environ.get(
            "COPAW_SUPABASE_JWT_SECRET",
            "",
        ).strip()


@dataclass
class Session:
    """Session data structure."""

    username: str
    created_at: float
    expires_at: float


@dataclass
class SessionManager:
    """Session manager with file persistence."""

    sessions: dict[str, Session] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._load()

    def _get_sessions_file(self) -> Path:
        return WORKING_DIR / "sessions.json"

    def _load(self) -> None:
        sessions_file = self._get_sessions_file()
        if not sessions_file.exists():
            return
        try:
            with open(sessions_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.sessions = {
                token: Session(**session_data)
                for token, session_data in data.items()
            }
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to load sessions file: %s", exc)
            self.sessions = {}

    def _save(self) -> None:
        sessions_file = self._get_sessions_file()
        sessions_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                token: {
                    "username": session.username,
                    "created_at": session.created_at,
                    "expires_at": session.expires_at,
                }
                for token, session in self.sessions.items()
            }
            with open(sessions_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Failed to save sessions file: %s", exc)

    def create_session(self, username: str, expire_hours: int) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        self.sessions[token] = Session(
            username=username,
            created_at=now,
            expires_at=now + expire_hours * 3600,
        )
        self._save()
        return token

    def validate_session(self, token: str) -> Optional[str]:
        session = self.sessions.get(token)
        if session is None:
            return None
        if time.time() > session.expires_at:
            del self.sessions[token]
            self._save()
            return None
        return session.username

    def delete_session(self, token: str) -> None:
        if token in self.sessions:
            del self.sessions[token]
            self._save()


# Global instances
auth_config = AuthConfig()
session_manager = SessionManager()


def _get_cookie_token(request: Request) -> Optional[str]:
    return request.cookies.get("copaw_session")


def _get_bearer_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def get_supabase_jwks() -> Optional[list[dict[str, Any]]]:
    """Fetch Supabase JWKS with caching.

    Returns cached keys if available and not expired (1 hour cache).
    """
    global _jwks_cache

    # Return cached keys if valid
    if _jwks_cache["keys"] and _jwks_cache["expires_at"] > time.time():
        return _jwks_cache["keys"]

    url = auth_config.supabase_url
    if not url:
        return None

    jwks_url = f"{url}/auth/v1/jwks"
    try:
        response = httpx.get(jwks_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        keys = data.get("keys", [])
        if keys:
            _jwks_cache["keys"] = keys
            _jwks_cache["expires_at"] = time.time() + 3600  # Cache for 1 hour
            logger.debug("Successfully fetched %d JWKS keys from Supabase", len(keys))
        return keys
    except Exception as e:
        logger.error("Failed to fetch JWKS from %s: %s", jwks_url, e)
        return None


def verify_supabase_jwt(token: str) -> Optional[str]:
    """Validate Supabase JWT using JWKS for ES256 signature verification.

    Supabase uses ES256 (ECDSA) algorithm for JWT signing. This function
    fetches the public keys from Supabase's JWKS endpoint and verifies
    the token signature.

    Falls back to HMAC verification if JWKS fails and jwt_secret is configured.
    """
    try:
        # Decode header to get kid and alg
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        alg = header.get("alg", "ES256")

        if kid:
            # Try JWKS verification for ES256 tokens
            keys = get_supabase_jwks()
            if keys:
                for key in keys:
                    if key.get("kid") == kid:
                        try:
                            public_key = jwk.construct(key)
                            payload = jwt.decode(
                                token,
                                public_key,
                                algorithms=[alg],
                                options={"verify_aud": False},
                            )
                            sub = payload.get("sub")
                            if sub:
                                logger.debug(
                                    "JWT verified via JWKS for user: %s",
                                    sub[:8] + "..."
                                )
                                return normalize_user_id(str(sub))
                        except JWTError as e:
                            logger.warning("JWT verification failed with JWKS key: %s", e)
                            continue
                        except Exception as e:
                            logger.warning("Unexpected error with JWKS key: %s", e)
                            continue

                logger.warning("No matching JWKS key found for kid: %s", kid)

        # Fallback to HMAC verification if jwt_secret is configured
        secret = auth_config.supabase_jwt_secret
        if secret:
            try:
                payload = jwt.decode(
                    token,
                    secret,
                    algorithms=["HS256", "HS384", "HS512"],
                    options={"verify_aud": False},
                )
                sub = payload.get("sub")
                if sub:
                    logger.debug("JWT verified via HMAC secret for user: %s", sub[:8] + "...")
                    return normalize_user_id(str(sub))
            except JWTError:
                pass

        return None

    except JWTError as e:
        logger.warning("JWT validation failed: %s", str(e))
        return None
    except Exception as e:
        logger.error("Unexpected error validating JWT: %s", str(e))
        return None


def is_public_path(path: str) -> bool:
    """Check if path should be accessible without authentication."""
    public_paths = {
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/status",
        "/api/auth/supabase-config",
        "/api/version",
        "/logo.png",
        "/copaw-symbol.svg",
    }
    if path in public_paths:
        return True
    if path.startswith("/assets/"):
        return True
    # Keep file share behavior unchanged.
    if path.startswith("/api/workspace/file/"):
        return True
    return False


def resolve_authenticated_user(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Resolve authenticated user from cookie session or bearer token."""
    # 1) Legacy cookie session.
    cookie_token = _get_cookie_token(request)
    if cookie_token:
        username = session_manager.validate_session(cookie_token)
        if username:
            return DEFAULT_USER_ID, "legacy"

    # 2) Authorization bearer.
    bearer = _get_bearer_token(request)
    if not bearer:
        return None, None

    supabase_user_id = verify_supabase_jwt(bearer)
    if supabase_user_id:
        return supabase_user_id, "supabase"

    # Backward compatibility: legacy session token in Authorization header.
    username = session_manager.validate_session(bearer)
    if username:
        return DEFAULT_USER_ID, "legacy"

    return None, None


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication middleware for protecting API routes."""

    async def dispatch(self, request: Request, call_next):
        if not auth_config.enabled:
            request.state.user_id = DEFAULT_USER_ID
            request.state.auth_mode = "disabled"
            return await call_next(request)

        path = request.url.path
        if is_public_path(path):
            return await call_next(request)

        user_id, auth_mode = resolve_authenticated_user(request)
        if user_id:
            request.state.user_id = user_id
            request.state.auth_mode = auth_mode
            return await call_next(request)

        # APIs require auth; non-API pages are handled by SPA routing.
        if path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )
        return await call_next(request)


def setup_auth(app) -> None:
    """Setup authentication routes and middleware."""
    from fastapi import Body, HTTPException

    @app.post("/api/auth/login")
    async def login(
        username: str = Body(...),
        password: str = Body(...),
    ):
        if not auth_config.enabled:
            return {"message": "Authentication is disabled"}

        if username != auth_config.username or password != auth_config.password:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        token = session_manager.create_session(
            username=username,
            expire_hours=auth_config.session_expire_hours,
        )
        response = JSONResponse(
            content={
                "message": "Login successful",
                "username": username,
                "user_id": DEFAULT_USER_ID,
                "auth_mode": "legacy",
            },
        )
        response.set_cookie(
            key="copaw_session",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=auth_config.session_expire_hours * 3600,
        )
        return response

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        cookie_token = _get_cookie_token(request)
        if cookie_token:
            session_manager.delete_session(cookie_token)

        bearer = _get_bearer_token(request)
        if bearer:
            session_manager.delete_session(bearer)

        response = JSONResponse(content={"message": "Logged out"})
        response.delete_cookie("copaw_session")
        return response

    @app.get("/api/auth/supabase-config")
    async def supabase_config():
        if auth_config.supabase_url and auth_config.supabase_anon_key:
            return {
                "supabase_url": auth_config.supabase_url,
                "supabase_anon_key": auth_config.supabase_anon_key,
            }
        return {
            "supabase_url": None,
            "supabase_anon_key": None,
        }

    @app.get("/api/auth/status")
    async def auth_status(request: Request):
        if not auth_config.enabled:
            return {
                "authenticated": True,
                "auth_enabled": False,
                "user_id": DEFAULT_USER_ID,
                "auth_mode": "disabled",
            }

        user_id, auth_mode = resolve_authenticated_user(request)
        if user_id:
            return {
                "authenticated": True,
                "auth_enabled": True,
                "user_id": user_id,
                "auth_mode": auth_mode,
            }
        return {
            "authenticated": False,
            "auth_enabled": True,
            "user_id": None,
            "auth_mode": None,
        }

    app.add_middleware(AuthMiddleware)
