"""
Storage backends for OAuth data.

Supports:
- In-memory storage (for local development)
- Redis storage (for Vercel/serverless with Upstash)
"""

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

# OAuth settings (TTLs in seconds)
AUTHORIZATION_CODE_EXPIRY = 300  # 5 minutes
ACCESS_TOKEN_EXPIRY = 3600  # 1 hour
REFRESH_TOKEN_EXPIRY = 86400  # 24 hours


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class AuthorizationCode:
    """Represents an OAuth authorization code."""

    code: str
    client_id: str
    redirect_uri: str
    scope: str
    state: str
    code_challenge: str
    code_challenge_method: str
    user_name: str
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        return time.time() - self.created_at > AUTHORIZATION_CODE_EXPIRY


@dataclass
class AccessToken:
    """Represents an OAuth access token."""

    token: str
    client_id: str
    user_name: str
    scope: str
    created_at: float = field(default_factory=time.time)
    expires_in: int = ACCESS_TOKEN_EXPIRY

    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.expires_in


@dataclass
class RefreshToken:
    """Represents an OAuth refresh token."""

    token: str
    client_id: str
    user_name: str
    scope: str
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        return time.time() - self.created_at > REFRESH_TOKEN_EXPIRY


@dataclass
class PendingAuthorization:
    """Represents a pending authorization request (user hasn't entered name yet)."""

    client_id: str
    redirect_uri: str
    scope: str
    state: str
    code_challenge: str
    code_challenge_method: str
    created_at: float = field(default_factory=time.time)


# ============================================================================
# Abstract Storage Interface
# ============================================================================


class OAuthStore(ABC):
    """Abstract base class for OAuth storage."""

    @abstractmethod
    def register_client(self, client_id: str, client_info: dict[str, Any]) -> None:
        """Register a client (for dynamic registration)."""
        pass

    @abstractmethod
    def get_client(self, client_id: str) -> dict[str, Any] | None:
        """Get a registered client."""
        pass

    @abstractmethod
    def store_pending_auth(self, auth_id: str, pending: PendingAuthorization) -> None:
        """Store a pending authorization."""
        pass

    @abstractmethod
    def get_pending_auth(self, auth_id: str) -> PendingAuthorization | None:
        """Get a pending authorization."""
        pass

    @abstractmethod
    def remove_pending_auth(self, auth_id: str) -> None:
        """Remove a pending authorization."""
        pass

    @abstractmethod
    def store_auth_code(self, code: AuthorizationCode) -> None:
        """Store an authorization code."""
        pass

    @abstractmethod
    def get_auth_code(self, code: str) -> AuthorizationCode | None:
        """Get and validate an authorization code."""
        pass

    @abstractmethod
    def consume_auth_code(self, code: str) -> AuthorizationCode | None:
        """Get and remove an authorization code (single use)."""
        pass

    @abstractmethod
    def store_access_token(self, token: AccessToken) -> None:
        """Store an access token."""
        pass

    @abstractmethod
    def get_access_token(self, token: str) -> AccessToken | None:
        """Get and validate an access token."""
        pass

    @abstractmethod
    def store_refresh_token(self, token: RefreshToken) -> None:
        """Store a refresh token."""
        pass

    @abstractmethod
    def get_refresh_token(self, token: str) -> RefreshToken | None:
        """Get and validate a refresh token."""
        pass

    @abstractmethod
    def revoke_refresh_token(self, token: str) -> None:
        """Revoke a refresh token."""
        pass


# ============================================================================
# In-Memory Storage (for local development)
# ============================================================================


class InMemoryOAuthStore(OAuthStore):
    """In-memory storage for OAuth data."""

    def __init__(self):
        self.authorization_codes: dict[str, AuthorizationCode] = {}
        self.access_tokens: dict[str, AccessToken] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}
        self.pending_authorizations: dict[str, PendingAuthorization] = {}
        self.registered_clients: dict[str, dict[str, Any]] = {}

    def register_client(self, client_id: str, client_info: dict[str, Any]) -> None:
        self.registered_clients[client_id] = client_info

    def get_client(self, client_id: str) -> dict[str, Any] | None:
        return self.registered_clients.get(client_id)

    def store_pending_auth(self, auth_id: str, pending: PendingAuthorization) -> None:
        self.pending_authorizations[auth_id] = pending

    def get_pending_auth(self, auth_id: str) -> PendingAuthorization | None:
        return self.pending_authorizations.get(auth_id)

    def remove_pending_auth(self, auth_id: str) -> None:
        self.pending_authorizations.pop(auth_id, None)

    def store_auth_code(self, code: AuthorizationCode) -> None:
        self.authorization_codes[code.code] = code

    def get_auth_code(self, code: str) -> AuthorizationCode | None:
        auth_code = self.authorization_codes.get(code)
        if auth_code and not auth_code.is_expired():
            return auth_code
        if auth_code:
            del self.authorization_codes[code]
        return None

    def consume_auth_code(self, code: str) -> AuthorizationCode | None:
        auth_code = self.get_auth_code(code)
        if auth_code:
            del self.authorization_codes[code]
        return auth_code

    def store_access_token(self, token: AccessToken) -> None:
        self.access_tokens[token.token] = token

    def get_access_token(self, token: str) -> AccessToken | None:
        access_token = self.access_tokens.get(token)
        if access_token and not access_token.is_expired():
            return access_token
        if access_token:
            del self.access_tokens[token]
        return None

    def store_refresh_token(self, token: RefreshToken) -> None:
        self.refresh_tokens[token.token] = token

    def get_refresh_token(self, token: str) -> RefreshToken | None:
        refresh_token = self.refresh_tokens.get(token)
        if refresh_token and not refresh_token.is_expired():
            return refresh_token
        if refresh_token:
            del self.refresh_tokens[token]
        return None

    def revoke_refresh_token(self, token: str) -> None:
        self.refresh_tokens.pop(token, None)


# ============================================================================
# Redis Storage (for Vercel/serverless)
# ============================================================================


class RedisOAuthStore(OAuthStore):
    """Redis-backed storage for OAuth data (works with Upstash)."""

    def __init__(self, redis_url: str):
        import redis
        self.redis = redis.from_url(redis_url)
        self._prefix = "mcp-oauth:"

    def _key(self, namespace: str, key: str) -> str:
        return f"{self._prefix}{namespace}:{key}"

    def _serialize(self, obj: Any) -> str:
        if hasattr(obj, "__dataclass_fields__"):
            return json.dumps(asdict(obj))
        return json.dumps(obj)

    def _deserialize_auth_code(self, data: str | None) -> AuthorizationCode | None:
        if not data:
            return None
        d = json.loads(data)
        return AuthorizationCode(**d)

    def _deserialize_access_token(self, data: str | None) -> AccessToken | None:
        if not data:
            return None
        d = json.loads(data)
        return AccessToken(**d)

    def _deserialize_refresh_token(self, data: str | None) -> RefreshToken | None:
        if not data:
            return None
        d = json.loads(data)
        return RefreshToken(**d)

    def _deserialize_pending_auth(self, data: str | None) -> PendingAuthorization | None:
        if not data:
            return None
        d = json.loads(data)
        return PendingAuthorization(**d)

    def register_client(self, client_id: str, client_info: dict[str, Any]) -> None:
        key = self._key("client", client_id)
        # Clients don't expire
        self.redis.set(key, self._serialize(client_info))

    def get_client(self, client_id: str) -> dict[str, Any] | None:
        key = self._key("client", client_id)
        data = self.redis.get(key)
        if data:
            return json.loads(data)
        return None

    def store_pending_auth(self, auth_id: str, pending: PendingAuthorization) -> None:
        key = self._key("pending", auth_id)
        self.redis.setex(key, AUTHORIZATION_CODE_EXPIRY, self._serialize(pending))

    def get_pending_auth(self, auth_id: str) -> PendingAuthorization | None:
        key = self._key("pending", auth_id)
        data = self.redis.get(key)
        return self._deserialize_pending_auth(data)

    def remove_pending_auth(self, auth_id: str) -> None:
        key = self._key("pending", auth_id)
        self.redis.delete(key)

    def store_auth_code(self, code: AuthorizationCode) -> None:
        key = self._key("authcode", code.code)
        self.redis.setex(key, AUTHORIZATION_CODE_EXPIRY, self._serialize(code))

    def get_auth_code(self, code: str) -> AuthorizationCode | None:
        key = self._key("authcode", code)
        data = self.redis.get(key)
        auth_code = self._deserialize_auth_code(data)
        if auth_code and auth_code.is_expired():
            self.redis.delete(key)
            return None
        return auth_code

    def consume_auth_code(self, code: str) -> AuthorizationCode | None:
        key = self._key("authcode", code)
        # Use GETDEL for atomic get-and-delete (Redis 6.2+)
        # Fall back to GET + DELETE for older versions
        try:
            data = self.redis.getdel(key)
        except AttributeError:
            data = self.redis.get(key)
            if data:
                self.redis.delete(key)
        
        auth_code = self._deserialize_auth_code(data)
        if auth_code and auth_code.is_expired():
            return None
        return auth_code

    def store_access_token(self, token: AccessToken) -> None:
        key = self._key("access", token.token)
        self.redis.setex(key, token.expires_in, self._serialize(token))

    def get_access_token(self, token: str) -> AccessToken | None:
        key = self._key("access", token)
        data = self.redis.get(key)
        access_token = self._deserialize_access_token(data)
        if access_token and access_token.is_expired():
            self.redis.delete(key)
            return None
        return access_token

    def store_refresh_token(self, token: RefreshToken) -> None:
        key = self._key("refresh", token.token)
        self.redis.setex(key, REFRESH_TOKEN_EXPIRY, self._serialize(token))

    def get_refresh_token(self, token: str) -> RefreshToken | None:
        key = self._key("refresh", token)
        data = self.redis.get(key)
        refresh_token = self._deserialize_refresh_token(data)
        if refresh_token and refresh_token.is_expired():
            self.redis.delete(key)
            return None
        return refresh_token

    def revoke_refresh_token(self, token: str) -> None:
        key = self._key("refresh", token)
        self.redis.delete(key)


# ============================================================================
# Factory Function
# ============================================================================


def create_oauth_store() -> OAuthStore:
    """
    Create the appropriate OAuth store based on environment.
    
    Uses Redis if REDIS_URL or UPSTASH_REDIS_REST_URL is set,
    otherwise falls back to in-memory storage.
    """
    # Check for Redis URL (Upstash or standard Redis)
    redis_url = os.environ.get("REDIS_URL") or os.environ.get("KV_URL")
    
    if redis_url:
        try:
            store = RedisOAuthStore(redis_url)
            # Test connection
            store.redis.ping()
            print(f"Using Redis storage", file=__import__("sys").stderr)
            return store
        except Exception as e:
            print(f"Redis connection failed: {e}, falling back to in-memory", file=__import__("sys").stderr)
    
    print("Using in-memory storage (data will not persist across requests in serverless)", file=__import__("sys").stderr)
    return InMemoryOAuthStore()
