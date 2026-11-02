"""Exercise real authenticated planning tools, without pretending a local script is an LLM."""
import pytest
from sqlalchemy import select

from app.auth import digest, mint_tool_context
from app.models import AuthSession
from conftest import login


@pytest.mark.parametrize("profile", ["mei-lin", "sam-rivera", "amina-ali"])
@pytest.mark.parametrize("tool,body", [
    ("get_student_profile", {}), ("get_school_adapter", {}),
    ("calculate_deadline", {"workflow": "program_extension"}),
    ("list_action_tasks", {}), ("get_policy_changes_for_profile", {}),
    ("build_action_plan", {}), ("search_official_policy", {"query": "program extension"}),
    ("escalate_to_isss", {"reason": "Check documents"}),
])
def test_authenticated_planning_tool_matrix(env, profile, tool, body):
    client, factory = env
    headers = login(client, profile)
    with factory() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(headers["Authorization"][7:])))
        context = mint_tool_context(session)
    response = client.post("/tools/" + tool, json=body, headers={
        "X-Tool-Key": "test-tool-key", "X-Staytus-Context": context})
    assert response.status_code == 200, response.text
    assert "mock" not in response.json().get("mode", "")
    if tool == "get_student_profile":
        assert response.json()["id"] == profile
    if tool == "search_official_policy":
        assert response.json()["policies"] == []
