"""
Production-ready logging configuration
- Structured JSON logs for easy parsing
- Sensitive data masking
- Performance monitoring
- Error tracking
"""
import logging
import json
import time
import re
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import sys

class SensitiveDataFilter(logging.Filter):
    """Filter to mask sensitive data in logs"""
    
    SENSITIVE_PATTERNS = {
        'phone': r'\b(\+?90)?5\d{9}\b',
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'api_key': r'(sk-[a-zA-Z0-9]{48}|Bearer\s+[a-zA-Z0-9\-_]+)',
        'password': r'("password"\s*:\s*")[^"]+(")',
        'pin': r'("pin"\s*:\s*")[^"]+(")',
        'token': r'(eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)',
    }
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Mask sensitive data in log messages"""
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = self._mask_sensitive(record.msg)
        
        if hasattr(record, 'args') and record.args:
            record.args = tuple(
                self._mask_sensitive(str(arg)) if isinstance(arg, (str, int, float)) else arg
                for arg in record.args
            )
        
        return True
    
    def _mask_sensitive(self, text: str) -> str:
        """Replace sensitive patterns with masked versions"""
        for name, pattern in self.SENSITIVE_PATTERNS.items():
            if name == 'phone':
                text = re.sub(pattern, '+90***MASKED', text)
            elif name == 'email':
                text = re.sub(pattern, '***@***.***', text)
            elif name == 'api_key':
                text = re.sub(pattern, '***API_KEY_MASKED***', text)
            elif name == 'password':
                text = re.sub(pattern, r'\1***MASKED***\2', text)
            elif name == 'pin':
                text = re.sub(pattern, r'\1****\2', text)
            elif name == 'token':
                text = re.sub(pattern, '***TOKEN_MASKED***', text)
        return text


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, 'user_id'):
            log_data['user_id'] = getattr(record, 'user_id')
        if hasattr(record, 'request_id'):
            log_data['request_id'] = getattr(record, 'request_id')
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = getattr(record, 'duration_ms')
        
        return json.dumps(log_data, ensure_ascii=False)


class PerformanceLogger:
    """Context manager for logging operation performance"""
    
    def __init__(self, logger: logging.Logger, operation: str, **context: Any):
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time: Optional[float] = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.logger.info(f"🚀 Starting: {self.operation}", extra=self.context)
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        duration_ms = int((time.time() - (self.start_time or 0)) * 1000)
        
        if exc_type is None:
            self.logger.info(
                f"✅ Completed: {self.operation} ({duration_ms}ms)",
                extra={**self.context, 'duration_ms': duration_ms}
            )
        else:
            self.logger.error(
                f"❌ Failed: {self.operation} ({duration_ms}ms) - {exc_val}",
                extra={**self.context, 'duration_ms': duration_ms},
                exc_info=True
            )


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
    mask_sensitive: bool = True
) -> logging.Logger:
    """
    Configure production logging
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON formatter for structured logs
        mask_sensitive: Enable sensitive data masking
    
    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger("pazarglobal")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    
    # Set formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    console_handler.setFormatter(formatter)
    
    # Add sensitive data filter
    if mask_sensitive:
        console_handler.addFilter(SensitiveDataFilter())
    
    logger.addHandler(console_handler)
    
    # Don't propagate to root logger
    logger.propagate = False
    
    return logger


# Global logger instance
logger = setup_logging(
    level="INFO",
    json_format=False,  # Set to True for production with log aggregation
    mask_sensitive=True
)
