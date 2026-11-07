"""Local single-account login for the combined web application.

Operational /auth routes are separate from the v1.1 procurement contract.
Business identity, scopes, and case membership remain server-derived.
"""
from collections import defaultdict, deque
from hashlib import sha256, scrypt
import hmac
import secrets
from threading import RLock
import time
from uuid import uuid4

from fastapi import Request
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.api.response import ApiError, failure, success
from app.core.config import ROOT
from app.schemas.shared import StrictModel

COOKIE = "procuremind_session"


class LoginSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="PROCUREMIND_LOGIN_", extra="ignore")
    enabled: bool = True
    username: str = "admin"
    password: SecretStr | None = None
    session_seconds: int = Field(default=8 * 60 * 60, ge=60, le=86400)

    @model_validator(mode="after")
    def credentials_required(self):
        if self.enabled and (not self.username or not self.password or len(self.password.get_secret_value()) < 8):
            raise ValueError("Configure a login username and a password of at least eight characters")
        return self


class LoginInput(StrictModel):
    username: str = Field(min_length=1, max_length=80)
    password: SecretStr = Field(min_length=1, max_length=256)


class Sessions:
    def __init__(self, config: LoginSettings):
        self.config = config
        self.salt = secrets.token_bytes(16)
        self.password_hash = self.digest(config.password.get_secret_value())
        self.tokens: dict[str, float] = {}
        self.failures: dict[str, deque] = defaultdict(deque)
        self.lock = RLock()

    def digest(self, password: str) -> bytes:
        return scrypt(password.encode(), salt=self.salt, n=16384, r=8, p=1)

    def valid(self, token: str | None) -> bool:
        if not token or len(token) > 128:
            return False
        key = sha256(token.encode()).hexdigest()
        with self.lock:
            expires = self.tokens.get(key, 0)
            if expires <= time.monotonic():
                self.tokens.pop(key, None)
                return False
            return True

    def revoke(self, token: str | None):
        if token:
            with self.lock:
                self.tokens.pop(sha256(token.encode()).hexdigest(), None)

    def authenticate(self, username: str, password: str, address: str) -> str:
        now = time.monotonic()
        with self.lock:
            for key in list(self.failures):
                while self.failures[key] and self.failures[key][0] <= now - 60:
                    self.failures[key].popleft()
                if not self.failures[key]:
                    del self.failures[key]
            attempts = self.failures[address]
            if len(attempts) >= 5 or len(self.failures) > 1024:
                raise ApiError(429, "RATE_LIMITED", "Too many login attempts. Try again in one minute.", retryable=True)
            # Session records keep only token hashes, never credentials.
            valid_password = hmac.compare_digest(self.digest(password), self.password_hash)
            valid_user = hmac.compare_digest(username.encode(), self.config.username.encode())
            if not (valid_user and valid_password):
                attempts.append(now)
                raise ApiError(401, "AUTHENTICATION_REQUIRED", "Username or password is incorrect")
            self.failures.pop(address, None)
            self.tokens = {key: expiry for key, expiry in self.tokens.items() if expiry > now}
            if len(self.tokens) >= 1024:
                self.tokens.pop(min(self.tokens, key=self.tokens.get))
            token = secrets.token_urlsafe(32)
            self.tokens[sha256(token.encode()).hexdigest()] = now + self.config.session_seconds
            return token


def install_login(app, config: LoginSettings):
    sessions = Sessions(config) if config.enabled else None
    app.state.login_sessions = sessions

    @app.middleware("http")
    async def require_login(request: Request, call_next):
        if sessions and request.url.path.startswith("/api/v1/") and request.url.path != "/api/v1/health":
            if not sessions.valid(request.cookies.get(COOKIE)):
                correlation_id = f"req_{uuid4().hex}"
                response = failure(ApiError(401, "AUTHENTICATION_REQUIRED", "Sign in to continue"), correlation_id)
                response.headers["X-Request-ID"] = correlation_id
                response.headers["Cache-Control"] = "no-store"
                response.delete_cookie(COOKIE, path="/")
                return response
        if sessions and request.url.path.startswith("/api/v1/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
                correlation_id = f"req_{uuid4().hex}"
                response = failure(ApiError(403, "FORBIDDEN", "Cross-origin request is not allowed"), correlation_id)
                response.headers["X-Request-ID"] = correlation_id
                return response
        response = await call_next(request)
        if request.url.path.startswith(("/auth/", "/api/v1/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    def request_id(request):
        return getattr(request.state, "request_id", f"req_{uuid4().hex}")

    def same_origin(request):
        origin = request.headers.get("origin")
        own_origin = f"{request.url.scheme}://{request.headers.get('host')}"
        if origin and origin != own_origin:
            raise ApiError(403, "FORBIDDEN", "Cross-origin login request is not allowed")

    @app.get("/auth/session", include_in_schema=False)
    def session_status(request: Request):
        authenticated = sessions is None or sessions.valid(request.cookies.get(COOKIE))
        return success({"authenticated": authenticated,
                        "username": config.username if authenticated else None,
                        "login_enabled": config.enabled}, request_id(request))

    @app.post("/auth/login", include_in_schema=False)
    def login(request: Request, payload: LoginInput):
        same_origin(request)
        if sessions is None:
            raise ApiError(403, "FORBIDDEN", "Login is disabled for this server")
        try:
            token = sessions.authenticate(payload.username, payload.password.get_secret_value(), request.client.host if request.client else "unknown")
        except ApiError as error:
            if error.status != 429:
                raise
            response = failure(error, request_id(request))
            response.headers["Retry-After"] = "60"
            return response
        sessions.revoke(request.cookies.get(COOKIE))
        response = success({"authenticated": True, "username": config.username, "login_enabled": True}, request_id(request))
        response.set_cookie(COOKIE, token, httponly=True, secure=request.url.scheme == "https",
                            samesite="strict", max_age=config.session_seconds, path="/")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/auth/logout", include_in_schema=False)
    def logout(request: Request):
        same_origin(request)
        if sessions:
            sessions.revoke(request.cookies.get(COOKIE))
        response = success({"authenticated": False, "username": None, "login_enabled": config.enabled}, request_id(request))
        response.delete_cookie(COOKIE, path="/")
        response.headers["Cache-Control"] = "no-store"
        return response
