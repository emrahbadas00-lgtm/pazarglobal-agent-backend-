"""
Security Middleware for Production
Provides rate limiting, input validation, and security headers
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict, Optional, List, Tuple, Any
import time
from collections import defaultdict
import re

# In-memory rate limiter (use Redis for production scaling)
class RateLimiter:
    def __init__(self):
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self.blocked: Dict[str, float] = {}
    
    def is_allowed(self, identifier: str, max_requests: int = 100, window: int = 60) -> Tuple[bool, Optional[str]]:
        """
        Check if request is allowed based on rate limits
        Args:
            identifier: user_id or IP address
            max_requests: max requests per window
            window: time window in seconds
        Returns:
            (is_allowed, error_message)
        """
        now = time.time()
        
        # Check if blocked
        if identifier in self.blocked:
            if now < self.blocked[identifier]:
                remaining = int(self.blocked[identifier] - now)
                return False, f"Too many requests. Try again in {remaining} seconds."
            else:
                del self.blocked[identifier]
        
        # Clean old requests
        cutoff = now - window
        self.requests[identifier] = [req_time for req_time in self.requests[identifier] if req_time > cutoff]
        
        # Check limit
        if len(self.requests[identifier]) >= max_requests:
            # Block for 5 minutes
            self.blocked[identifier] = now + 300
            return False, "Rate limit exceeded. Blocked for 5 minutes."
        
        # Add current request
        self.requests[identifier] = self.requests[identifier][-max_requests:] + [now]
        return True, None


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Production security middleware
    - Rate limiting
    - Input validation
    - Security headers
    - Request sanitization
    """
    
    def __init__(self, app: Any, rate_limiter: RateLimiter):
        super().__init__(app)
        self.rate_limiter = rate_limiter
        
        # Dangerous patterns to block
        self.sql_injection_patterns: List[str] = [
            r"(\bunion\b.*\bselect\b)",
            r"(\bselect\b.*\bfrom\b)",
            r"(\bdrop\b.*\btable\b)",
            r"(\binsert\b.*\binto\b)",
            r"(\bdelete\b.*\bfrom\b)",
            r"(\bexec\b.*\()",
            r"(\bscript\b.*\>)",
        ]
        self.xss_patterns: List[str] = [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"onerror\s*=",
            r"onload\s*=",
        ]
    
    async def dispatch(self, request: Request, call_next: Any):
        # Skip security for health check
        if request.url.path == "/" or request.url.path == "/health":
            response = await call_next(request)
            return self._add_security_headers(response)
        
        # Get identifier (user_id from body or IP)
        identifier = self._get_identifier(request)
        
        # Rate limiting
        is_allowed, error_msg = self.rate_limiter.is_allowed(identifier, max_requests=100, window=60)
        if not is_allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "rate_limit_exceeded", "message": error_msg}
            )
        
        # Input validation for POST requests
        if request.method == "POST":
            try:
                body = await request.body()
                body_str = body.decode("utf-8", errors="ignore")
                
                # Check for SQL injection
                if self._contains_dangerous_pattern(body_str, self.sql_injection_patterns):
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"error": "invalid_input", "message": "Suspicious input detected"}
                    )
                
                # Check for XSS
                if self._contains_dangerous_pattern(body_str, self.xss_patterns):
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"error": "invalid_input", "message": "Potentially harmful content detected"}
                    )
                
                # Recreate request with validated body
                request._body = body  # type: ignore[attr-defined]
            except Exception:
                pass  # If body already consumed, continue
        
        # Process request
        response = await call_next(request)
        
        # Add security headers
        return self._add_security_headers(response)
    
    def _get_identifier(self, request: Request) -> str:
        """Get user identifier for rate limiting"""
        # Try to get user_id from request state (set by auth middleware)
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"
        
        # Fall back to IP address
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        
        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"
    
    def _contains_dangerous_pattern(self, text: str, patterns: List[str]) -> bool:
        """Check if text contains dangerous patterns"""
        text_lower = text.lower()
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        return False
    
    def _add_security_headers(self, response: Any) -> Any:
        """Add security headers to response"""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response


# Global rate limiter instance
rate_limiter = RateLimiter()
