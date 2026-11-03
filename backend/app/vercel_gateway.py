"""Public narrow tool entrypoint with the existing independent dual authentication."""
from app.vercel_environment import prepare_environment

prepare_environment()

from app.tool_gateway import app  # noqa: F401
