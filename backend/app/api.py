from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services as svc
from app.auth import get_current_session, require_profile_session
from app.config import get_settings
from app.chat import ChatSettings
from app.db import get_db
from app.models import Approval, AuditEvent, AuthSession, Notification, Profile
from app.rules import adapter_for
from app.schemas import ApprovalConfirm, ApprovalInput, ProfileUpdate

router = APIRouter(prefix="/api/v1")


@router.post("/auth/logout")
def logout(session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    db.delete(session)
    return {"ok": True}


@router.get("/profile")
def profile(session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    return {**svc.profile_json(db.get(Profile, session.profile_id)), "role": session.role}


@router.patch("/profile")
def patch_profile(body: ProfileUpdate, session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    return svc.update_profile(db, db.get(Profile, session.profile_id), body)


@router.get("/school")
def school(session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    return adapter_for(db.get(Profile, session.profile_id)).metadata()


@router.get("/dashboard")
def dashboard(session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    p = db.get(Profile, session.profile_id)
    from app.workflow_guidance import build_workflow_guidance
    return {"profile": {**svc.profile_json(p), "role": session.role}, "deadlines": svc.deadlines(db, p), "tasks": svc.tasks_for(db, p),
            "workflow_guidance": build_workflow_guidance(db, p),
            "notifications": [svc.notification_json(n) for n in db.scalars(select(Notification).where(Notification.profile_id == p.id).order_by(Notification.created_at.desc()))],
            "mode": "live", "notice": "Your saved profile and internal planning reminders. Open the cited official sources to confirm current requirements; reminders are not official filing deadlines."}


@router.get("/policies")
def policies(q: str = "", include_pending: bool = True, session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    items = svc.search_policies(db, db.get(Profile, session.profile_id), q, include_pending)
    modes = sorted({item.get("retrieval_mode", "keyword") for item in items})
    return {"policies": items, "retrieval_mode": "+".join(modes) if modes else "keyword", "statuses": svc.POLICY_STATUSES}


@router.get("/approvals")
def approvals(session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    items = list(db.scalars(select(Approval).where(Approval.profile_id == session.profile_id).order_by(Approval.created_at.desc())))
    for a in items:
        svc.expire_approval(db, a)
    return {"approvals": [svc.approval_json(a) for a in items]}


@router.post("/approvals", status_code=201)
def new_approval(body: ApprovalInput, session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    return svc.approval_json(svc.propose(db, db.get(Profile, session.profile_id), body.kind, body.payload))


@router.post("/approvals/{approval_id}/preview")
def preview(approval_id: str, session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    return svc.approval_json(svc.preview(db, svc.get_approval(db, session.profile_id, approval_id)))


@router.post("/approvals/{approval_id}/approve")
def approve(approval_id: str, body: ApprovalConfirm, session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    a = svc.get_approval(db, session.profile_id, approval_id)
    return svc.approval_json(svc.execute(db, db.get(Profile, session.profile_id), a, body.payload_hash))


@router.post("/approvals/{approval_id}/reject")
def reject(approval_id: str, session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    a = svc.get_approval(db, session.profile_id, approval_id)
    if a.status not in ("PROPOSED", "PREVIEWED"):
        raise HTTPException(409, f"Cannot reject {a.status} approval")
    a.status = "REJECTED"
    svc.audit(db, session.profile_id, "approval.rejected", {"approval_id": a.id})
    return svc.approval_json(a)


@router.get("/approvals/{approval_id}/calendar.ics")
def ics(approval_id: str, session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    a = svc.get_approval(db, session.profile_id, approval_id)
    if a.kind != "calendar" or a.status != "SUCCEEDED":
        raise HTTPException(409, "Approve the calendar preview before exporting it")
    if a.payload.get("provider", "export") != "export":
        raise HTTPException(409, "This approval targets a connected calendar; create a separate export preview if you need a file")
    return Response(svc.calendar_ics(a), media_type="text/calendar", headers={"Content-Disposition": 'attachment; filename="staytus-reminder.ics"'})


@router.get("/audit")
def audit(session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    items = db.scalars(select(AuditEvent).where(AuditEvent.profile_id == session.profile_id).order_by(AuditEvent.created_at.desc()).limit(200))
    return {"events": [{"id": i.id, "action": i.action, "detail": i.detail, "created_at": svc.iso(i.created_at), "correlation_id": i.correlation_id} for i in items]}


@router.get("/integration-status")
def integration_status(session: AuthSession = Depends(get_current_session)):
    config = get_settings()
    chat = ChatSettings()
    chat_credentials = bool(chat.orchestrate_api_key or chat.orchestrate_bearer_token)
    chat_configured = bool(chat.orchestrate_service_url and chat.orchestrate_agent_id and chat_credentials)
    watsonx_configured = bool(config.watsonx_url and config.watsonx_api_key and config.watsonx_project_id)
    embedding_configured = bool(watsonx_configured and config.watsonx_embedding_model)
    return {"agent_mode": "orchestrate", "orchestrate": {
                "configured": chat_configured,
                "service_url_configured": bool(chat.orchestrate_service_url),
                "agent_id_configured": bool(chat.orchestrate_agent_id),
                "credentials_configured": chat_credentials,
                "tool_key_configured": bool(config.tool_key),
                "secure_context_verified": chat.orchestrate_context_verified,
                "live_verified": False,
                "status": "configured_not_live_verified" if chat_configured and chat.orchestrate_context_verified else (
                    "context_verification_required" if chat_configured else "not_configured")},
            "watsonx": {"configured": watsonx_configured,
                "embedding_model_configured": bool(config.watsonx_embedding_model),
                "generation_model_configured": bool(config.watsonx_generation_model),
                "embeddings_configured": embedding_configured, "live_verified": False,
                "status": "not_live_verified" if watsonx_configured else "not_configured"},
            "database": "sqlite" if config.database_url.startswith("sqlite") else "postgresql",
            "retrieval": "hybrid_when_indexed" if embedding_configured else "keyword",
            "optional_semantic_retrieval_configured": embedding_configured,
            "chat_retrieval_service": "shared_policy_retrieval",
            "student_model_api_key_required": False,
            "retrieval_notice": "Chat, policy UI and Agent tools share one retrieval service. Each result reports the actual mode; configured models are not proof of successful inference.",
            "external_writes": "approval_required", "policy_worker_enabled": config.policy_worker_enabled}


