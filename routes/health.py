"""
Health check endpoints for monitoring and alerting
Monitors: Database, OpenAI API, Storage, System resources
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import os
import time
import httpx
import psutil
from datetime import datetime

router = APIRouter(prefix="/health", tags=["Health"])


class HealthStatus(BaseModel):
    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: str
    version: str
    checks: Dict[str, Dict[str, Any]]
    uptime_seconds: float


class ServiceCheck(BaseModel):
    status: str  # "up", "down", "degraded"
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


# Track service start time
SERVICE_START_TIME = time.time()


async def check_supabase() -> ServiceCheck:
    """Check Supabase database connection"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_key:
        return ServiceCheck(
            status="down",
            error="Supabase credentials not configured"
        )
    
    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{supabase_url}/rest/v1/",
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}"
                }
            )
            latency_ms = int((time.time() - start) * 1000)
            
            if response.status_code == 200:
                return ServiceCheck(
                    status="up",
                    latency_ms=latency_ms,
                    details={"endpoint": "supabase_rest_api"}
                )
            else:
                return ServiceCheck(
                    status="degraded",
                    latency_ms=latency_ms,
                    error=f"HTTP {response.status_code}"
                )
    except Exception as e:
        return ServiceCheck(
            status="down",
            error=str(e)
        )


async def check_openai() -> ServiceCheck:
    """Check OpenAI API availability"""
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        return ServiceCheck(
            status="down",
            error="OpenAI API key not configured"
        )
    
    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            latency_ms = int((time.time() - start) * 1000)
            
            if response.status_code == 200:
                return ServiceCheck(
                    status="up",
                    latency_ms=latency_ms,
                    details={"endpoint": "openai_api"}
                )
            else:
                return ServiceCheck(
                    status="degraded",
                    latency_ms=latency_ms,
                    error=f"HTTP {response.status_code}"
                )
    except Exception as e:
        return ServiceCheck(
            status="down",
            error=str(e)
        )


def check_system_resources() -> ServiceCheck:
    """Check system CPU and memory usage"""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Define thresholds
        cpu_warning = 80
        memory_warning = 85
        disk_warning = 90
        
        status = "up"
        warnings = []
        
        if cpu_percent > cpu_warning:
            status = "degraded"
            warnings.append(f"High CPU: {cpu_percent}%")
        
        if memory.percent > memory_warning:
            status = "degraded"
            warnings.append(f"High memory: {memory.percent}%")
        
        if disk.percent > disk_warning:
            status = "degraded"
            warnings.append(f"High disk usage: {disk.percent}%")
        
        return ServiceCheck(
            status=status,
            error=", ".join(warnings) if warnings else None,
            details={
                "cpu_percent": round(cpu_percent, 1),
                "memory_percent": round(memory.percent, 1),
                "memory_available_mb": round(memory.available / 1024 / 1024, 1),
                "disk_percent": round(disk.percent, 1),
                "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 1)
            }
        )
    except Exception as e:
        return ServiceCheck(
            status="down",
            error=str(e)
        )


@router.get("/", response_model=HealthStatus)
async def health_check():
    """
    Comprehensive health check endpoint
    Returns system health status and dependencies
    """
    # Run all health checks
    supabase = await check_supabase()
    openai = await check_openai()
    system = check_system_resources()
    
    checks = {
        "supabase": supabase.dict(),
        "openai": openai.dict(),
        "system": system.dict()
    }
    
    # Determine overall status
    statuses = [supabase.status, openai.status, system.status]
    
    if all(s == "up" for s in statuses):
        overall_status = "healthy"
    elif any(s == "down" for s in statuses):
        overall_status = "unhealthy"
    else:
        overall_status = "degraded"
    
    uptime = time.time() - SERVICE_START_TIME
    
    return HealthStatus(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat() + 'Z',
        version="2.0.0",
        checks=checks,
        uptime_seconds=round(uptime, 1)
    )


@router.get("/ready")
async def readiness_check():
    """
    Kubernetes readiness probe
    Returns 200 if service is ready to accept traffic
    """
    supabase = await check_supabase()
    openai = await check_openai()
    
    if supabase.status == "down" or openai.status == "down":
        raise HTTPException(
            status_code=503,
            detail="Service not ready: dependencies unavailable"
        )
    
    return {"status": "ready"}


@router.get("/live")
async def liveness_check():
    """
    Kubernetes liveness probe
    Returns 200 if service is alive (basic check)
    """
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat() + 'Z'}
