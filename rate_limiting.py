"""
Rate limiting middleware for block explorer API
Protects against abuse and ensures fair resource usage
"""

import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass
from collections import defaultdict
from functools import wraps
from flask import request, jsonify

logger = logging.getLogger(__name__)


@dataclass
class RateLimitRule:
    """Rate limit rule configuration"""
    requests: int  # Number of requests
    window: int  # Time window in seconds
    burst: int = 0  # Burst allowance


@dataclass
class RateLimitState:
    """Track rate limit state for a client"""
    requests: list[float]  # Timestamps of requests
    blocked_until: Optional[float] = None


class RateLimiter:
    """Rate limiting with multiple strategies"""

    def __init__(self):
        # Default rules
        self.rules = {
            "default": RateLimitRule(requests=100, window=60, burst=10),
            "search": RateLimitRule(requests=30, window=60, burst=5),
            "websocket": RateLimitRule(requests=10, window=60, burst=2),
            "analytics": RateLimitRule(requests=20, window=60, burst=3),
        }

        # Client states
        self.states: Dict[str, RateLimitState] = defaultdict(
            lambda: RateLimitState(requests=[])
        )

        # IP-based blocking
        self.blocked_ips: Dict[str, float] = {}

        # Statistics
        self.stats = {
            "total_requests": 0,
            "blocked_requests": 0,
            "unique_clients": set(),
        }

    def check_rate_limit(
        self, client_id: str, rule_name: str = "default"
    ) -> tuple[bool, Optional[Dict]]:
        """
        Check if request is within rate limit
        Returns (allowed, info)
        """
        self.stats["total_requests"] += 1
        self.stats["unique_clients"].add(client_id)

        # Check if IP is blocked
        if client_id in self.blocked_ips:
            blocked_until = self.blocked_ips[client_id]
            if time.time() < blocked_until:
                self.stats["blocked_requests"] += 1
                return False, {
                    "error": "IP temporarily blocked",
                    "blocked_until": blocked_until,
                    "retry_after": int(blocked_until - time.time()),
                }
            else:
                # Unblock
                del self.blocked_ips[client_id]

        # Get rule and state
        rule = self.rules.get(rule_name, self.rules["default"])
        state = self.states[client_id]

        # Check if client is temporarily blocked
        if state.blocked_until and time.time() < state.blocked_until:
            self.stats["blocked_requests"] += 1
            return False, {
                "error": "Rate limit exceeded",
                "retry_after": int(state.blocked_until - time.time()),
            }

        current_time = time.time()
        window_start = current_time - rule.window

        # Remove old requests outside the window
        state.requests = [ts for ts in state.requests if ts > window_start]

        # Check rate limit
        if len(state.requests) >= rule.requests:
            # Block for the remainder of the window
            state.blocked_until = state.requests[0] + rule.window
            self.stats["blocked_requests"] += 1

            return False, {
                "error": "Rate limit exceeded",
                "limit": rule.requests,
                "window": rule.window,
                "retry_after": int(state.blocked_until - current_time),
            }

        # Add current request
        state.requests.append(current_time)

        # Return rate limit info
        remaining = rule.requests - len(state.requests)
        reset_time = state.requests[0] + rule.window if state.requests else current_time

        return True, {
            "limit": rule.requests,
            "remaining": remaining,
            "reset": int(reset_time),
            "window": rule.window,
        }

    def block_ip(self, ip: str, duration: int = 3600) -> None:
        """Block an IP address for a duration (seconds)"""
        self.blocked_ips[ip] = time.time() + duration
        logger.warning(f"Blocked IP {ip} for {duration} seconds")

    def unblock_ip(self, ip: str) -> None:
        """Unblock an IP address"""
        if ip in self.blocked_ips:
            del self.blocked_ips[ip]
            logger.info(f"Unblocked IP {ip}")

    def reset_client(self, client_id: str) -> None:
        """Reset rate limit state for a client"""
        if client_id in self.states:
            del self.states[client_id]

    def get_stats(self) -> Dict:
        """Get rate limiter statistics"""
        return {
            "total_requests": self.stats["total_requests"],
            "blocked_requests": self.stats["blocked_requests"],
            "unique_clients": len(self.stats["unique_clients"]),
            "blocked_ips": len(self.blocked_ips),
            "active_clients": len(self.states),
            "block_rate": (
                (self.stats["blocked_requests"] / self.stats["total_requests"] * 100)
                if self.stats["total_requests"] > 0
                else 0
            ),
        }


class IPWhitelist:
    """Manage IP whitelist for rate limiting bypass"""

    def __init__(self):
        self.whitelist: set[str] = set()

    def add(self, ip: str) -> None:
        """Add IP to whitelist"""
        self.whitelist.add(ip)
        logger.info(f"Added {ip} to whitelist")

    def remove(self, ip: str) -> None:
        """Remove IP from whitelist"""
        self.whitelist.discard(ip)
        logger.info(f"Removed {ip} from whitelist")

    def is_whitelisted(self, ip: str) -> bool:
        """Check if IP is whitelisted"""
        return ip in self.whitelist


class AbuseDetector:
    """Detect and prevent API abuse"""

    def __init__(self, rate_limiter: RateLimiter):
        self.rate_limiter = rate_limiter
        self.suspicious_patterns: Dict[str, int] = defaultdict(int)

    def check_request_pattern(self, client_id: str, endpoint: str) -> bool:
        """
        Check for suspicious request patterns
        Returns True if request should be blocked
        """
        pattern_key = f"{client_id}:{endpoint}"

        # Track rapid repeated requests to same endpoint
        self.suspicious_patterns[pattern_key] += 1

        # If client is hitting same endpoint excessively
        if self.suspicious_patterns[pattern_key] > 50:
            logger.warning(f"Suspicious pattern detected for {client_id} on {endpoint}")
            self.rate_limiter.block_ip(client_id, duration=1800)  # 30 min
            return True

        return False

    def check_user_agent(self, user_agent: str) -> bool:
        """
        Check for suspicious user agents
        Returns True if request should be blocked
        """
        if not user_agent:
            return False

        # List of suspicious patterns
        suspicious_agents = [
            "scanner",
            "bot",
            "crawler",
            "scraper",
            "wget",
            "curl",  # Could allow curl with auth
        ]

        user_agent_lower = user_agent.lower()
        for pattern in suspicious_agents:
            if pattern in user_agent_lower:
                logger.warning(f"Suspicious user agent: {user_agent}")
                return True

        return False

    def reset_pattern(self, client_id: str) -> None:
        """Reset pattern tracking for client"""
        keys_to_remove = [k for k in self.suspicious_patterns if k.startswith(client_id)]
        for key in keys_to_remove:
            del self.suspicious_patterns[key]


# Flask middleware
def rate_limit(rule_name: str = "default"):
    """Decorator for rate limiting Flask routes"""

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get client identifier
            client_id = request.remote_addr

            # Get rate limiter from app context
            rate_limiter = getattr(f, "_rate_limiter", None)
            if not rate_limiter:
                # No rate limiter configured, allow request
                return f(*args, **kwargs)

            # Check rate limit
            allowed, info = rate_limiter.check_rate_limit(client_id, rule_name)

            if not allowed:
                response = jsonify(info)
                response.status_code = 429  # Too Many Requests
                if "retry_after" in info:
                    response.headers["Retry-After"] = str(info["retry_after"])
                return response

            # Add rate limit headers
            response = f(*args, **kwargs)
            if hasattr(response, "headers") and info:
                response.headers["X-RateLimit-Limit"] = str(info.get("limit", 0))
                response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", 0))
                response.headers["X-RateLimit-Reset"] = str(info.get("reset", 0))

            return response

        return wrapped

    return decorator


def create_rate_limit_middleware(app, rate_limiter: RateLimiter):
    """Create Flask middleware for rate limiting"""

    @app.before_request
    def check_rate_limit():
        # Skip rate limiting for certain paths
        if request.path in ["/health", "/metrics"]:
            return None

        client_id = request.remote_addr

        # Determine rule based on endpoint
        rule_name = "default"
        if "/search" in request.path:
            rule_name = "search"
        elif "/ws" in request.path:
            rule_name = "websocket"
        elif "/analytics" in request.path:
            rule_name = "analytics"

        # Check rate limit
        allowed, info = rate_limiter.check_rate_limit(client_id, rule_name)

        if not allowed:
            response = jsonify(info)
            response.status_code = 429
            if "retry_after" in info:
                response.headers["Retry-After"] = str(info["retry_after"])
            return response

        return None
