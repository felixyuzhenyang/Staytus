from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services as svc
from app.auth import get_tool_session
from app.db import get_db
from app.models import AuthSession, Notification, Profile
from app.rules import adapter_for
from app.schemas import DeadlineTool, EmptyTool, EscalationTool, PolicyTool, PreviewTool, SearchTool
from app.integrations.connectors import MailReadTool, read_recent_messages
from app.mail_analysis import MailAnalysisTool, analyze_matching_messages

router = APIRouter(prefix="/tools", tags=["Orchestrate read and proposal tools"])


def actor(db: Session, session: AuthSession, tool: str):
    svc.audit(db, session.profile_id, f"tool.{tool}", {"channel": "orchestrate"})
    return db.get(Profile, session.profile_id)


@router.post("/get_student_profile", operation_id="get_student_profile")
def get_student_profile(body: EmptyTool, session: AuthSession = Depends(get_tool_session), db: Session = Depends(get_db)):
    return svc.profile_json(actor(db, session, "get_student_profile"))


@router.post("/get_school_adapter", operation_id="get_school_adapter")
def get_school_adapter(body: EmptyTool, session: AuthSession = Depends(get_tool_session), db: Session = Depends(get_db)):
    return adapter_for(actor(db, session, "get_school_adapter")).metadata()


@router.post("/search_official_policy", operation_id="search_official_policy")
def search_official_policy(body: SearchTool, session: AuthSession = Depends(get_tool_session), db: Session = Depends(get_db)):
    return {"policies": svc.search_policies(db, actor(db, session, "search_official_policy"), body.query, body.include_pending)}


@router.post("/get_policy_version_and_status", operation_id="get_policy_version_and_status")
def get_policy_version_and_status(body: PolicyTool, session: AuthSession = Depends(get_tool_session), db: Session = Depends(get_db)):
    profile = actor(db, session, "get_policy_version_and_status")
    from app.retrieval import search_snapshots
    policies = search_snapshots(db, "", profile.status_type, include_pending=True,
                               include_fixtures=False, school=profile.school,
                               policy_version_id=body.policy_version_id, limit=1)
    if not policies:
        raise HTTPException(404, "Policy version not found")
    return policies[0]


@router.post("/calculate_deadline", operation_id="calculate_deadline")
def calculate_deadline(body: DeadlineTool, session: AuthSession = Depends(get_tool_session), db: Session = Depends(get_db)):
    return {"deadlines": [r for r in svc.deadlines(db, actor(db, session, "calculate_deadline")) if r["workflow"] == body.workflow]}


@router.post("/list_action_tasks", operation_id="list_action_tasks")
def list_action_tasks(body: EmptyTool, session: AuthSession = Depends(get_tool_session), db: Session = Depends(get_db)):
    return {"tasks": svc.tasks_for(db, actor(db, session, "list_action_tasks"))}


@router.post("/get_policy_changes_for_profile", operation_id="get_policy_changes_for_profile")
def get_policy_changes_for_profile(body: EmptyTool, session: AuthSession = Depends(get_tool_session), db: Session = Depends(get_db)):
    actor(db, session, "get_policy_changes_for_profile")
    return {"changes": [svc.notification_json(n) for n in db.scalars(select(Notification).where(Notification.profile_id == session.profile_id).order_by(Notification.created_at.desc()))]}


@router.post("/escalate_to_isss", operation_id="escalate_to_isss")
def escalate_to_isss(body: EscalationTool, session: AuthSession = Depends(get_tool_session), db: Session = Depends(get_db)):
    profile = actor(db, session, "escalate_to_isss")
    return {**adapter_for(profile).metadata(), "reason": body.reason, "action": "Contact your assigned adviser through ISSS / iPenn; no message sent"}


@router.post("/build_action_plan", operation_id="build_action_plan")
def build_action_plan(body: EmptyTool, session: AuthSession = Depends(get_tool_session), db: Session = Depends(get_db)):
    profile = actor(db, session, "build_action_plan")
    from app.workflow_guidance import build_workflow_guidance
    return {"tasks": svc.tasks_for(db, profile), "deadlines": svc.deadlines(db, profile),
            "workflow_guidance": build_workflow_guidance(db, profile)}


@router.post("/propose_profile_update", operation_id="propose_profile_update")
def propose_profile_update(body: PreviewTool, session: AuthSession = Depends(get_tool_session), db: Session = Depends(get_db)):
    return svc.approval_json(svc.propose(db, actor(db, session, "propose_profile_update"), "profile_update", body.payload))


@router.post("/create_email_preview", operation_id="create_email_preview")
def create_email_preview(body: PreviewTool, session: AuthSession = Depends(get_tool_session), db: Session = Depends(get_db)):
    return svc.approval_json(svc.propose(db, actor(db, session, "create_email_preview"), "email", body.payload))


@router.post("/create_calendar_preview", operation_id="create_calendar_preview")
def create_calendar_preview(body: PreviewTool, session: AuthSession = Depends(get_tool_session), db: Session = Depends(get_db)):
    return svc.approval_json(svc.propose(db, actor(db, session, "create_calendar_preview"), "calendar", body.payload))


@router.post("/read_recent_official_messages", operation_id="read_recent_official_messages")
def read_recent_official_messages(body: MailReadTool, session: AuthSession = Depends(get_tool_session), db: Session = Depends(get_db)):
    profile = actor(db, session, "read_recent_official_messages")
    return read_recent_messages(db, profile.account_id, body.provider, limit=body.limit, for_agent=True)


@router.post("/summarize_recent_official_messages", operation_id="summarize_recent_official_messages")
def summarize_recent_official_messages(body: MailAnalysisTool, session: AuthSession = Depends(get_tool_session),
                                       db: Session = Depends(get_db)):
    profile = actor(db, session, "summarize_recent_official_messages")
    return {"provider": body.provider,
        "analyses": analyze_matching_messages(db, profile.account_id, profile, body.provider, limit=body.limit),
        "raw_bodies_retained": False,
        "notice": "Summaries are planning aids; verify dates and required actions in the original mailbox and official sources."}
