"""
User-friendly error handling and messages
Maps technical errors to friendly Turkish messages
"""
from typing import Dict, Any, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
import logging

logger = logging.getLogger("pazarglobal")


class ErrorResponse:
    """Standard error response format"""
    
    def __init__(
        self,
        code: str,
        message: str,
        user_message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        self.code = code
        self.message = message
        self.user_message = user_message
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "user_message": self.user_message,
                "details": self.details
            }
        }


# User-friendly error messages in Turkish
ERROR_MESSAGES = {
    # Authentication
    "not_authenticated": "Oturum açmanız gerekiyor. Lütfen telefon numaranızla giriş yapın.",
    "invalid_credentials": "Telefon numarası veya PIN hatalı. Lütfen tekrar deneyin.",
    "session_expired": "Oturumunuz sona erdi. Lütfen tekrar giriş yapın.",
    "blocked": "Hesabınız geçici olarak kilitlendi. Lütfen daha sonra tekrar deneyin.",
    
    # Rate limiting
    "rate_limit_exceeded": "Çok fazla istek gönderdiniz. Lütfen birkaç dakika bekleyip tekrar deneyin.",
    
    # Validation
    "invalid_input": "Girdiğiniz bilgiler geçersiz. Lütfen kontrol edip tekrar deneyin.",
    "missing_required_field": "Zorunlu alanlar eksik. Lütfen tüm bilgileri doldurun.",
    "invalid_phone": "Telefon numarası geçersiz. Lütfen +90 ile başlayan 13 haneli numara girin.",
    "invalid_price": "Fiyat geçersiz. Lütfen sayısal bir değer girin.",
    
    # Database
    "database_error": "Veritabanı hatası. Lütfen daha sonra tekrar deneyin.",
    "not_found": "Aradığınız ilan bulunamadı.",
    "duplicate_entry": "Bu ilan zaten mevcut.",
    
    # Authorization
    "permission_denied": "Bu işlem için yetkiniz yok.",
    "not_owner": "Sadece kendi ilanlarınızı düzenleyebilir veya silebilirsiniz.",
    
    # File upload
    "file_too_large": "Dosya boyutu çok büyük. Maksimum 5MB yükleyebilirsiniz.",
    "invalid_file_type": "Geçersiz dosya tipi. Sadece JPG, PNG veya WEBP yükleyebilirsiniz.",
    "upload_failed": "Dosya yüklenemedi. Lütfen tekrar deneyin.",
    
    # AI/Agent
    "agent_error": "İsteğinizi işlerken bir hata oluştu. Lütfen tekrar deneyin.",
    "openai_error": "AI servisi şu anda müsait değil. Lütfen daha sonra tekrar deneyin.",
    "content_blocked": "İçeriğiniz güvenlik politikalarımıza uymuyor.",
    
    # General
    "server_error": "Sunucu hatası. Lütfen daha sonra tekrar deneyin.",
    "service_unavailable": "Servis şu anda kullanılamıyor. Lütfen daha sonra tekrar deneyin.",
    "timeout": "İstek zaman aşımına uğradı. Lütfen tekrar deneyin.",
}


def get_user_friendly_message(error_code: str, default: Optional[str] = None) -> str:
    """Get user-friendly Turkish message for error code"""
    return ERROR_MESSAGES.get(
        error_code,
        default or "Bir hata oluştu. Lütfen daha sonra tekrar deneyin."
    )


def create_error_response(
    error_code: str,
    technical_message: str,
    details: Optional[Dict[str, Any]] = None,
    status_code: int = status.HTTP_400_BAD_REQUEST
) -> JSONResponse:
    """
    Create standardized error response
    
    Args:
        error_code: Machine-readable error code
        technical_message: Technical error message (logged)
        details: Additional error details
        status_code: HTTP status code
    
    Returns:
        JSONResponse with user-friendly error
    """
    user_message = get_user_friendly_message(error_code)
    
    error_response = ErrorResponse(
        code=error_code,
        message=technical_message,
        user_message=user_message,
        details=details
    )
    
    # Log technical details
    logger.error(f"Error [{error_code}]: {technical_message}", extra=details or {})
    
    return JSONResponse(
        status_code=status_code,
        content=error_response.to_dict()
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors with friendly messages"""
    errors: list[Dict[str, Any]] = []
    for error in exc.errors():
        field = ".".join(str(x) for x in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })
    
    return create_error_response(
        error_code="invalid_input",
        technical_message=f"Validation failed: {errors}",
        details={"validation_errors": errors},
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions with safe error messages"""
    # Don't expose internal error details to users
    logger.exception("Unhandled exception", exc_info=exc)
    
    return create_error_response(
        error_code="server_error",
        technical_message=str(exc),
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def register_error_handlers(app: Any) -> None:
    """Register all error handlers with FastAPI app"""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
