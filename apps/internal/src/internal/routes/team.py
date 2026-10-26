# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Team AI admin routes for HTML pages.

Provides admin views for the Team AI orchestration platform.

Scopes required:
- team:read - View team data
- team:write - Create/update team resources
- team:delete - Delete team resources
"""

import json

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from internal import TEMPLATES_DIR
from internal.auth.dependencies import require_resource_scopes_or_redirect
from internal.auth.models import User
from internal.logging import get_logger
from internal.services.team_client import team_client

router = APIRouter(prefix="/team", tags=["team"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)

# Scope dependencies
require_team_read = require_resource_scopes_or_redirect("team")
require_team_write = require_resource_scopes_or_redirect("team", required_scope="team:write")


# =============================================================================
# Dashboard (Teams list)
# =============================================================================


@router.get("", response_class=HTMLResponse)
async def team_dashboard(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_team_read),
):
    """Team dashboard - overview of all teams."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    teams = await team_client.list_teams()

    return templates.TemplateResponse(
        request=request,
        name="admin/team/dashboard.html",
        context={
            "request": request,
            "active_section": "team",
            "user": user,
            "teams": teams,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


# =============================================================================
# Teams CRUD
# =============================================================================


@router.get("/new", response_class=HTMLResponse)
async def team_new(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """New team form."""
    if not isinstance(auth_result, User):
        return auth_result

    return templates.TemplateResponse(
        request=request,
        name="admin/team/team_form.html",
        context={
            "request": request,
            "active_section": "team",
            "user": auth_result,
            "team": None,
            "is_edit": False,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/new")
async def team_create(
    request: Request,
    name: str = Form(...),
    slug: str = Form(...),
    description: str = Form(""),
    config_json: str = Form("{}"),
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Create a new team."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    try:
        config = json.loads(config_json) if config_json else {}
    except json.JSONDecodeError:
        return RedirectResponse(
            url="/team/new?error=Invalid+JSON+in+config",
            status_code=303,
        )

    team = await team_client.create_team(
        name=name,
        slug=slug,
        description=description or None,
        config=config,
    )

    if team:
        logger.info("Team created | user_id=%s team_id=%s name=%s", user.id, team.id, team.name)
        return RedirectResponse(
            url=f"/team/{team.id}?success=Team+created+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url="/team/new?error=Failed+to+create+team",
        status_code=303,
    )


@router.get("/{team_id}", response_class=HTMLResponse)
async def team_detail(
    request: Request,
    team_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_read),
):
    """Team detail view with agents, workflows, conversations."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    agents = await team_client.list_agents(team_id, limit=10)
    workflows = await team_client.list_workflows(team_id, limit=10)
    memory = await team_client.list_memory(team_id, limit=10)

    return templates.TemplateResponse(
        request=request,
        name="admin/team/team_detail.html",
        context={
            "request": request,
            "active_section": "team",
            "user": user,
            "team": team,
            "agents": agents,
            "workflows": workflows,
            "memory": memory,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{team_id}/edit", response_class=HTMLResponse)
async def team_edit(
    request: Request,
    team_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Edit team form."""
    if not isinstance(auth_result, User):
        return auth_result

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="admin/team/team_form.html",
        context={
            "request": request,
            "active_section": "team",
            "user": auth_result,
            "team": team,
            "is_edit": True,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/{team_id}/edit")
async def team_update(
    request: Request,
    team_id: str,
    name: str = Form(...),
    description: str = Form(""),
    config_json: str = Form("{}"),
    is_active: bool = Form(True),
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Update a team."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    try:
        config = json.loads(config_json) if config_json else {}
    except json.JSONDecodeError:
        return RedirectResponse(
            url=f"/team/{team_id}/edit?error=Invalid+JSON+in+config",
            status_code=303,
        )

    team = await team_client.update_team(
        team_id=team_id,
        name=name,
        description=description or None,
        config=config,
        is_active=is_active,
    )

    if team:
        logger.info("Team updated | user_id=%s team_id=%s", user.id, team_id)
        return RedirectResponse(
            url=f"/team/{team_id}?success=Team+updated+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/edit?error=Failed+to+update+team",
        status_code=303,
    )


@router.post("/{team_id}/delete")
async def team_delete(
    request: Request,
    team_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Delete a team."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    success = await team_client.delete_team(team_id)

    if success:
        logger.info("Team deleted | user_id=%s team_id=%s", user.id, team_id)
        return RedirectResponse(
            url="/team?success=Team+deleted+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}?error=Failed+to+delete+team",
        status_code=303,
    )


# =============================================================================
# Agents CRUD
# =============================================================================


@router.get("/{team_id}/agents", response_class=HTMLResponse)
async def agents_list(
    request: Request,
    team_id: str,
    page: int = Query(1, ge=1),
    auth_result: User | RedirectResponse = Depends(require_team_read),
):
    """List agents for a team."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    per_page = 20
    offset = (page - 1) * per_page

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    agents = await team_client.list_agents(team_id, limit=per_page, offset=offset)

    return templates.TemplateResponse(
        request=request,
        name="admin/team/agents_list.html",
        context={
            "request": request,
            "active_section": "team",
            "user": user,
            "team": team,
            "agents": agents,
            "page": page,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{team_id}/agents/new", response_class=HTMLResponse)
async def agent_new(
    request: Request,
    team_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """New agent form."""
    if not isinstance(auth_result, User):
        return auth_result

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    available_tools = await team_client.list_tools()

    return templates.TemplateResponse(
        request=request,
        name="admin/team/agent_form.html",
        context={
            "request": request,
            "active_section": "team",
            "user": auth_result,
            "team": team,
            "agent": None,
            "is_edit": False,
            "available_tools": available_tools,
            "advanced_config": {},
            "error": request.query_params.get("error"),
        },
    )


@router.post("/{team_id}/agents/new")
async def agent_create(
    request: Request,
    team_id: str,
    name: str = Form(...),
    role: str = Form(...),
    description: str = Form(""),
    system_prompt: str = Form(""),
    model: str = Form("gpt-4o"),
    provider: str = Form("openai"),
    config_json: str = Form("{}"),
    max_iterations: int = Form(10),
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Create a new agent."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    try:
        config = json.loads(config_json) if config_json else {}
    except json.JSONDecodeError:
        return RedirectResponse(
            url=f"/team/{team_id}/agents/new?error=Invalid+JSON+in+config",
            status_code=303,
        )

    # Merge structured fields into config
    form = await request.form()
    config["tools"] = [str(t) for t in form.getlist("tools")]
    config["max_iterations"] = max_iterations

    cred_keys = form.getlist("credential_keys")
    cred_values = form.getlist("credential_values")
    credentials = {}
    for key, value in zip(cred_keys, cred_values, strict=False):
        k, v = str(key).strip(), str(value).strip()
        if k and v:
            credentials[k] = v
    if credentials:
        config["credentials"] = credentials

    agent = await team_client.create_agent(
        team_id=team_id,
        name=name,
        role=role,
        description=description or None,
        system_prompt=system_prompt or None,
        model=model,
        provider=provider,
        config=config,
    )

    if agent:
        logger.info(
            "Agent created | user_id=%s team_id=%s agent_id=%s name=%s",
            user.id,
            team_id,
            agent.id,
            agent.name,
        )
        return RedirectResponse(
            url=f"/team/{team_id}/agents/{agent.id}?success=Agent+created+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/agents/new?error=Failed+to+create+agent",
        status_code=303,
    )


@router.get("/{team_id}/agents/{agent_id}", response_class=HTMLResponse)
async def agent_detail(
    request: Request,
    team_id: str,
    agent_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_read),
):
    """Agent detail view."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    agent = await team_client.get_agent(team_id, agent_id)
    if not agent:
        return RedirectResponse(
            url=f"/team/{team_id}/agents?error=Agent+not+found",
            status_code=303,
        )

    skills = await team_client.list_skills(team_id, agent_id)

    return templates.TemplateResponse(
        request=request,
        name="admin/team/agent_detail.html",
        context={
            "request": request,
            "active_section": "team",
            "user": user,
            "team": team,
            "agent": agent,
            "skills": skills,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{team_id}/agents/{agent_id}/edit", response_class=HTMLResponse)
async def agent_edit(
    request: Request,
    team_id: str,
    agent_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Edit agent form."""
    if not isinstance(auth_result, User):
        return auth_result

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    agent = await team_client.get_agent(team_id, agent_id)
    if not agent:
        return RedirectResponse(
            url=f"/team/{team_id}/agents?error=Agent+not+found",
            status_code=303,
        )

    skills = await team_client.list_skills(team_id, agent_id)
    available_tools = await team_client.list_tools()
    advanced_config = {
        k: v
        for k, v in (agent.config or {}).items()
        if k not in ("tools", "max_iterations", "credentials")
    }

    return templates.TemplateResponse(
        request=request,
        name="admin/team/agent_form.html",
        context={
            "request": request,
            "active_section": "team",
            "user": auth_result,
            "team": team,
            "agent": agent,
            "skills": skills,
            "is_edit": True,
            "available_tools": available_tools,
            "advanced_config": advanced_config,
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/{team_id}/agents/{agent_id}/edit")
async def agent_update(
    request: Request,
    team_id: str,
    agent_id: str,
    name: str = Form(...),
    role: str = Form(...),
    description: str = Form(""),
    system_prompt: str = Form(""),
    model: str = Form("gpt-4o"),
    provider: str = Form("openai"),
    config_json: str = Form("{}"),
    max_iterations: int = Form(10),
    is_active: bool = Form(True),
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Update an agent."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    try:
        config = json.loads(config_json) if config_json else {}
    except json.JSONDecodeError:
        return RedirectResponse(
            url=f"/team/{team_id}/agents/{agent_id}/edit?error=Invalid+JSON+in+config",
            status_code=303,
        )

    # Merge structured fields into config
    form = await request.form()
    config["tools"] = [str(t) for t in form.getlist("tools")]
    config["max_iterations"] = max_iterations

    # Credentials: merge with existing (empty values = keep existing)
    existing_agent = await team_client.get_agent(team_id, agent_id)
    existing_credentials = {}
    if existing_agent and existing_agent.config:
        existing_credentials = existing_agent.config.get("credentials", {})
    cred_keys = form.getlist("credential_keys")
    cred_values = form.getlist("credential_values")
    cred_remove = {str(r) for r in form.getlist("credential_remove")}

    credentials = {}
    for key, value in zip(cred_keys, cred_values, strict=False):
        k, v = str(key).strip(), str(value).strip()
        if not k or k in cred_remove:
            continue
        if v:
            credentials[k] = v
        elif k in existing_credentials:
            credentials[k] = existing_credentials[k]
    config["credentials"] = credentials

    agent = await team_client.update_agent(
        team_id=team_id,
        agent_id=agent_id,
        name=name,
        role=role,
        description=description or None,
        system_prompt=system_prompt or None,
        model=model,
        provider=provider,
        config=config,
        is_active=is_active,
    )

    if agent:
        logger.info("Agent updated | user_id=%s team_id=%s agent_id=%s", user.id, team_id, agent_id)
        return RedirectResponse(
            url=f"/team/{team_id}/agents/{agent_id}?success=Agent+updated+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/agents/{agent_id}/edit?error=Failed+to+update+agent",
        status_code=303,
    )


@router.post("/{team_id}/agents/{agent_id}/delete")
async def agent_delete(
    request: Request,
    team_id: str,
    agent_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Delete an agent."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    success = await team_client.delete_agent(team_id, agent_id)

    if success:
        logger.info("Agent deleted | user_id=%s team_id=%s agent_id=%s", user.id, team_id, agent_id)
        return RedirectResponse(
            url=f"/team/{team_id}/agents?success=Agent+deleted+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/agents/{agent_id}?error=Failed+to+delete+agent",
        status_code=303,
    )


# =============================================================================
# Skills
# =============================================================================


@router.post("/{team_id}/agents/{agent_id}/skills/new")
async def skill_create(
    request: Request,
    team_id: str,
    agent_id: str,
    skill_name: str = Form(...),
    skill_description: str = Form(...),
    skill_content: str = Form(""),
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Create a new skill for an agent."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    form = await request.form()
    allowed_tools = [str(t) for t in form.getlist("skill_allowed_tools")]

    skill = await team_client.create_skill(
        team_id=team_id,
        agent_id=agent_id,
        name=skill_name,
        description=skill_description,
        content=skill_content,
        allowed_tools=allowed_tools,
    )

    if skill:
        logger.info(
            "Skill created | user_id=%s team_id=%s agent_id=%s skill=%s",
            user.id,
            team_id,
            agent_id,
            skill.name,
        )
        return RedirectResponse(
            url=f"/team/{team_id}/agents/{agent_id}/edit?success=Skill+created+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/agents/{agent_id}/edit?error=Failed+to+create+skill",
        status_code=303,
    )


@router.post("/{team_id}/agents/{agent_id}/skills/{skill_id}/delete")
async def skill_delete(
    request: Request,
    team_id: str,
    agent_id: str,
    skill_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Delete a skill."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    if await team_client.delete_skill(team_id, agent_id, skill_id):
        logger.info(
            "Skill deleted | user_id=%s team_id=%s agent_id=%s skill_id=%s",
            user.id,
            team_id,
            agent_id,
            skill_id,
        )
        return RedirectResponse(
            url=f"/team/{team_id}/agents/{agent_id}/edit?success=Skill+deleted",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/agents/{agent_id}/edit?error=Failed+to+delete+skill",
        status_code=303,
    )


@router.get("/{team_id}/agents/{agent_id}/skills/{skill_id}/edit", response_class=HTMLResponse)
async def skill_edit(
    request: Request,
    team_id: str,
    agent_id: str,
    skill_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Edit skill form."""
    if not isinstance(auth_result, User):
        return auth_result

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    agent = await team_client.get_agent(team_id, agent_id)
    if not agent:
        return RedirectResponse(
            url=f"/team/{team_id}/agents?error=Agent+not+found",
            status_code=303,
        )

    skill = await team_client.get_skill(team_id, agent_id, skill_id)
    if not skill:
        return RedirectResponse(
            url=f"/team/{team_id}/agents/{agent_id}/edit?error=Skill+not+found",
            status_code=303,
        )

    available_tools = await team_client.list_tools()

    return templates.TemplateResponse(
        request=request,
        name="admin/team/skill_form.html",
        context={
            "request": request,
            "active_section": "team",
            "user": auth_result,
            "team": team,
            "agent": agent,
            "skill": skill,
            "available_tools": available_tools,
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/{team_id}/agents/{agent_id}/skills/{skill_id}/edit")
async def skill_update(
    request: Request,
    team_id: str,
    agent_id: str,
    skill_id: str,
    skill_name: str = Form(...),
    skill_description: str = Form(...),
    skill_content: str = Form(""),
    is_active: bool = Form(True),
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Update a skill."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    form = await request.form()
    allowed_tools = [str(t) for t in form.getlist("skill_allowed_tools")]

    skill = await team_client.update_skill(
        team_id=team_id,
        agent_id=agent_id,
        skill_id=skill_id,
        name=skill_name,
        description=skill_description,
        content=skill_content,
        allowed_tools=allowed_tools,
        is_active=is_active,
    )

    if skill:
        logger.info(
            "Skill updated | user_id=%s team_id=%s agent_id=%s skill_id=%s",
            user.id,
            team_id,
            agent_id,
            skill_id,
        )
        return RedirectResponse(
            url=f"/team/{team_id}/agents/{agent_id}/edit?success=Skill+updated+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/agents/{agent_id}/skills/{skill_id}/edit?error=Failed+to+update+skill",
        status_code=303,
    )


# =============================================================================
# Workflows CRUD
# =============================================================================


@router.get("/{team_id}/workflows", response_class=HTMLResponse)
async def workflows_list(
    request: Request,
    team_id: str,
    page: int = Query(1, ge=1),
    auth_result: User | RedirectResponse = Depends(require_team_read),
):
    """List workflows for a team."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    per_page = 20
    offset = (page - 1) * per_page

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    workflows = await team_client.list_workflows(team_id, limit=per_page, offset=offset)

    return templates.TemplateResponse(
        request=request,
        name="admin/team/workflows_list.html",
        context={
            "request": request,
            "active_section": "team",
            "user": user,
            "team": team,
            "workflows": workflows,
            "page": page,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{team_id}/workflows/new", response_class=HTMLResponse)
async def workflow_new(
    request: Request,
    team_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """New workflow form."""
    if not isinstance(auth_result, User):
        return auth_result

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    agents = await team_client.list_agents(team_id)

    return templates.TemplateResponse(
        request=request,
        name="admin/team/workflow_form.html",
        context={
            "request": request,
            "active_section": "team",
            "user": auth_result,
            "team": team,
            "workflow": None,
            "agents": agents,
            "is_edit": False,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/{team_id}/workflows/new")
async def workflow_create(
    request: Request,
    team_id: str,
    name: str = Form(...),
    description: str = Form(""),
    steps_json: str = Form("{}"),
    config_json: str = Form("{}"),
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Create a new workflow."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    try:
        steps = json.loads(steps_json) if steps_json else {}
        config = json.loads(config_json) if config_json else {}
    except json.JSONDecodeError:
        return RedirectResponse(
            url=f"/team/{team_id}/workflows/new?error=Invalid+JSON+format",
            status_code=303,
        )

    workflow = await team_client.create_workflow(
        team_id=team_id,
        name=name,
        description=description or None,
        steps=steps,
        config=config,
    )

    if workflow:
        logger.info(
            "Workflow created | user_id=%s team_id=%s workflow_id=%s",
            user.id,
            team_id,
            workflow.id,
        )
        return RedirectResponse(
            url=f"/team/{team_id}/workflows?success=Workflow+created+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/workflows/new?error=Failed+to+create+workflow",
        status_code=303,
    )


@router.get("/{team_id}/workflows/{workflow_id}/edit", response_class=HTMLResponse)
async def workflow_edit(
    request: Request,
    team_id: str,
    workflow_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Edit workflow form."""
    if not isinstance(auth_result, User):
        return auth_result

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    workflows = await team_client.list_workflows(team_id)
    workflow = next((w for w in workflows if w.id == workflow_id), None)
    if not workflow:
        return RedirectResponse(
            url=f"/team/{team_id}/workflows?error=Workflow+not+found",
            status_code=303,
        )

    agents = await team_client.list_agents(team_id)

    return templates.TemplateResponse(
        request=request,
        name="admin/team/workflow_form.html",
        context={
            "request": request,
            "active_section": "team",
            "user": auth_result,
            "team": team,
            "workflow": workflow,
            "agents": agents,
            "is_edit": True,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/{team_id}/workflows/{workflow_id}/edit")
async def workflow_update(
    request: Request,
    team_id: str,
    workflow_id: str,
    name: str = Form(...),
    description: str = Form(""),
    steps_json: str = Form("{}"),
    workflow_status: str = Form("draft"),
    config_json: str = Form("{}"),
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Update a workflow."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    try:
        steps = json.loads(steps_json) if steps_json else {}
        config = json.loads(config_json) if config_json else {}
    except json.JSONDecodeError:
        return RedirectResponse(
            url=f"/team/{team_id}/workflows/{workflow_id}/edit?error=Invalid+JSON+format",
            status_code=303,
        )

    workflow = await team_client.update_workflow(
        team_id=team_id,
        workflow_id=workflow_id,
        name=name,
        description=description or None,
        steps=steps,
        status=workflow_status,
        config=config,
    )

    if workflow:
        logger.info(
            "Workflow updated | user_id=%s team_id=%s workflow_id=%s",
            user.id,
            team_id,
            workflow_id,
        )
        return RedirectResponse(
            url=f"/team/{team_id}/workflows?success=Workflow+updated+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/workflows/{workflow_id}/edit?error=Failed+to+update+workflow",
        status_code=303,
    )


@router.post("/{team_id}/workflows/{workflow_id}/delete")
async def workflow_delete(
    request: Request,
    team_id: str,
    workflow_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Delete a workflow."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    success = await team_client.delete_workflow(team_id, workflow_id)

    if success:
        logger.info(
            "Workflow deleted | user_id=%s team_id=%s workflow_id=%s",
            user.id,
            team_id,
            workflow_id,
        )
        return RedirectResponse(
            url=f"/team/{team_id}/workflows?success=Workflow+deleted+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/workflows?error=Failed+to+delete+workflow",
        status_code=303,
    )


# =============================================================================
# Run Agent (launch a task / conversation)
# =============================================================================


@router.get("/{team_id}/run", response_class=HTMLResponse)
async def run_agent_form(
    request: Request,
    team_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Show the form to launch an agent conversation."""
    if not isinstance(auth_result, User):
        return auth_result

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    agents = await team_client.list_agents(team_id)

    return templates.TemplateResponse(
        request=request,
        name="admin/team/run_form.html",
        context={
            "request": request,
            "active_section": "team",
            "user": auth_result,
            "team": team,
            "agents": agents,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/{team_id}/run")
async def run_agent_submit(
    request: Request,
    team_id: str,
    agent_id: str = Form(...),
    title: str = Form(...),
    message: str = Form(...),
    priority: int = Form(0),
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Create a task and trigger agent execution."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    task = await team_client.create_task(
        team_id=team_id,
        title=title,
        description=message,
        agent_id=agent_id,
        input_data={"prompt": message},
        priority=priority,
    )

    if task:
        logger.info(
            "Agent task launched | user_id=%s team_id=%s agent_id=%s task_id=%s",
            user.id,
            team_id,
            agent_id,
            task.id,
        )
        return RedirectResponse(
            url=f"/team/{team_id}/conversations?success=Agent+task+launched+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/run?error=Failed+to+launch+agent+task",
        status_code=303,
    )


# =============================================================================
# Conversations
# =============================================================================


@router.get("/{team_id}/conversations", response_class=HTMLResponse)
async def conversations_list(
    request: Request,
    team_id: str,
    page: int = Query(1, ge=1),
    auth_result: User | RedirectResponse = Depends(require_team_read),
):
    """List conversations."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    per_page = 20
    offset = (page - 1) * per_page

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    conversations = await team_client.list_conversations(limit=per_page, offset=offset)
    agents = await team_client.list_agents(team_id)
    agent_map = {a.id: a.name for a in agents}
    has_next = len(conversations) == per_page

    return templates.TemplateResponse(
        request=request,
        name="admin/team/conversations_list.html",
        context={
            "request": request,
            "active_section": "team",
            "user": user,
            "team": team,
            "conversations": conversations,
            "agent_map": agent_map,
            "page": page,
            "has_next": has_next,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{team_id}/conversations/{conv_id}", response_class=HTMLResponse)
async def conversation_detail(
    request: Request,
    team_id: str,
    conv_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_read),
):
    """Conversation detail with messages."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    conversation = await team_client.get_conversation(conv_id)
    if not conversation:
        return RedirectResponse(
            url=f"/team/{team_id}/conversations?error=Conversation+not+found",
            status_code=303,
        )

    messages = await team_client.list_messages(conv_id, limit=100)
    agents = await team_client.list_agents(team_id)
    agent_map = {a.id: a.name for a in agents}

    # Build tool_call_id -> tool_name mapping from assistant messages
    tool_call_map: dict[str, str] = {}
    for msg in messages:
        for tc in msg.content.get("tool_calls", []):
            tc_id = tc.get("id", "")
            tc_name = tc.get("function", {}).get("name", "")
            if tc_id and tc_name:
                tool_call_map[tc_id] = tc_name

    return templates.TemplateResponse(
        request=request,
        name="admin/team/conversation_detail.html",
        context={
            "request": request,
            "active_section": "team",
            "user": user,
            "team": team,
            "conversation": conversation,
            "messages": messages,
            "agent_map": agent_map,
            "tool_call_map": tool_call_map,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{team_id}/conversations/{conv_id}/status", response_class=JSONResponse)
async def conversation_status(
    request: Request,
    team_id: str,
    conv_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_read),
):
    """Get conversation status and message count as JSON (for polling)."""
    if not isinstance(auth_result, User):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    conversation = await team_client.get_conversation(conv_id)
    if not conversation:
        return JSONResponse({"error": "Not found"}, status_code=404)

    messages = await team_client.list_messages(conv_id, limit=100)

    return JSONResponse(
        {
            "status": conversation.status,
            "message_count": len(messages),
        }
    )


@router.post("/{team_id}/conversations/{conv_id}/delete")
async def conversation_delete(
    request: Request,
    team_id: str,
    conv_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Delete a conversation."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    success = await team_client.delete_conversation(conv_id)

    if success:
        logger.info(
            "Conversation deleted | user_id=%s team_id=%s conv_id=%s",
            user.id,
            team_id,
            conv_id,
        )
        return RedirectResponse(
            url=f"/team/{team_id}/conversations?success=Conversation+deleted+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/conversations/{conv_id}?error=Failed+to+delete+conversation",
        status_code=303,
    )


@router.post("/{team_id}/conversations/bulk-delete")
async def conversations_bulk_delete(
    request: Request,
    team_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Bulk delete conversations."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    form = await request.form()
    conv_ids = form.getlist("conversation_ids")

    if not conv_ids:
        return RedirectResponse(
            url=f"/team/{team_id}/conversations?error=No+conversations+selected",
            status_code=303,
        )

    deleted = 0
    for conv_id in conv_ids:
        if await team_client.delete_conversation(str(conv_id)):
            deleted += 1

    logger.info(
        "Bulk delete conversations | user_id=%s team_id=%s deleted=%d/%d",
        user.id,
        team_id,
        deleted,
        len(conv_ids),
    )
    return RedirectResponse(
        url=f"/team/{team_id}/conversations?success={deleted}+conversation(s)+deleted",
        status_code=303,
    )


@router.post("/{team_id}/conversations/{conv_id}/cancel-task")
async def conversation_cancel_task(
    request: Request,
    team_id: str,
    conv_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Cancel the task linked to a conversation."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    conversation = await team_client.get_conversation(conv_id)
    if not conversation:
        return RedirectResponse(
            url=f"/team/{team_id}/conversations?error=Conversation+not+found",
            status_code=303,
        )

    task_id = _extract_task_id(conversation.slug)
    if not task_id:
        return RedirectResponse(
            url=f"/team/{team_id}/conversations/{conv_id}?error=No+task+linked+to+this+conversation",
            status_code=303,
        )

    if await team_client.cancel_task(team_id, task_id):
        logger.info(
            "Task cancelled | user_id=%s team_id=%s task_id=%s conv_id=%s",
            user.id,
            team_id,
            task_id,
            conv_id,
        )
        return RedirectResponse(
            url=f"/team/{team_id}/conversations/{conv_id}?success=Task+cancelled+successfully",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/conversations/{conv_id}?error=Failed+to+cancel+task",
        status_code=303,
    )


@router.post("/{team_id}/conversations/bulk-cancel")
async def conversations_bulk_cancel(
    request: Request,
    team_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Bulk cancel tasks linked to conversations."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    form = await request.form()
    conv_ids = form.getlist("conversation_ids")

    if not conv_ids:
        return RedirectResponse(
            url=f"/team/{team_id}/conversations?error=No+conversations+selected",
            status_code=303,
        )

    cancelled = 0
    for conv_id in conv_ids:
        conversation = await team_client.get_conversation(str(conv_id))
        if not conversation:
            continue
        task_id = _extract_task_id(conversation.slug)
        if task_id and await team_client.cancel_task(team_id, task_id):
            cancelled += 1

    logger.info(
        "Bulk cancel tasks | user_id=%s team_id=%s cancelled=%d/%d",
        user.id,
        team_id,
        cancelled,
        len(conv_ids),
    )
    return RedirectResponse(
        url=f"/team/{team_id}/conversations?success={cancelled}+task(s)+cancelled",
        status_code=303,
    )


def _extract_task_id(slug: str) -> str | None:
    """Extract task ID from conversation slug (format: task-{uuid})."""
    if slug.startswith("task-"):
        return slug[5:]
    return None


# =============================================================================
# Memory
# =============================================================================


@router.get("/{team_id}/memory", response_class=HTMLResponse)
async def memory_list(
    request: Request,
    team_id: str,
    page: int = Query(1, ge=1),
    auth_result: User | RedirectResponse = Depends(require_team_read),
):
    """List memory entries for a team."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    per_page = 20
    offset = (page - 1) * per_page

    team = await team_client.get_team(team_id)
    if not team:
        return RedirectResponse(url="/team?error=Team+not+found", status_code=303)

    memory = await team_client.list_memory(team_id, limit=per_page, offset=offset)
    agents = await team_client.list_agents(team_id)
    agent_map = {a.id: a.name for a in agents}
    has_next = len(memory) == per_page

    return templates.TemplateResponse(
        request=request,
        name="admin/team/memory_list.html",
        context={
            "request": request,
            "active_section": "team",
            "user": user,
            "team": team,
            "memory": memory,
            "agent_map": agent_map,
            "page": page,
            "has_next": has_next,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/{team_id}/memory/{memory_id}/delete")
async def memory_delete(
    request: Request,
    team_id: str,
    memory_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Delete a single memory entry."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    if await team_client.delete_memory(team_id, memory_id):
        logger.info(
            "Memory entry deleted | user_id=%s team_id=%s memory_id=%s",
            user.id,
            team_id,
            memory_id,
        )
        return RedirectResponse(
            url=f"/team/{team_id}/memory?success=Memory+entry+deleted",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/team/{team_id}/memory?error=Failed+to+delete+memory+entry",
        status_code=303,
    )


@router.post("/{team_id}/memory/bulk-delete")
async def memory_bulk_delete(
    request: Request,
    team_id: str,
    auth_result: User | RedirectResponse = Depends(require_team_write),
):
    """Bulk delete memory entries."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    form = await request.form()
    memory_ids = form.getlist("memory_ids")

    if not memory_ids:
        return RedirectResponse(
            url=f"/team/{team_id}/memory?error=No+entries+selected",
            status_code=303,
        )

    deleted = 0
    for memory_id in memory_ids:
        if await team_client.delete_memory(team_id, str(memory_id)):
            deleted += 1

    logger.info(
        "Bulk delete memory | user_id=%s team_id=%s deleted=%d/%d",
        user.id,
        team_id,
        deleted,
        len(memory_ids),
    )
    return RedirectResponse(
        url=f"/team/{team_id}/memory?success={deleted}+entry(ies)+deleted",
        status_code=303,
    )
