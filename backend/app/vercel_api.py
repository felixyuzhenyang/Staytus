"""Private Vercel API service; only its authenticated cron routes have public ingress."""
from app.vercel_environment import prepare_environment

prepare_environment()

from app.main import app
from app.scheduled_jobs import router

app.include_router(router)
