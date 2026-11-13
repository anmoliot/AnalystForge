"""Versioned API router assembly."""

from fastapi import APIRouter

from analystforge.api.routers import meta

api_router = APIRouter()
api_router.include_router(meta.router)
