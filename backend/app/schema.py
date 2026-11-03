"""Register every application table without importing routers or starting workers."""
from app.db import Base


def metadata():
    from app import models, chat_models, policy_models, notification_models, mail_monitor_models  # noqa: F401
    from app.integrations import connection_models  # noqa: F401
    return Base.metadata
