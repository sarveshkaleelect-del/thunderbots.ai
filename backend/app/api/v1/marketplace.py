"""
Thunder Marketplace API.

Fully independent module:
- Does not import, modify, or depend on app.api.v1.workflows internals.
- Only ever INSERTs a new Workflow row (via /import) — never updates or
  deletes an existing workflow, never touches the AI engine, ThunderGuide,
  Knowledge Base, or auth logic.
- Catalog data is static Python (app.marketplace.catalog) — no DB tables,
  no startup preloading. Template graphs are generated on demand per-request.
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.workflow import Workflow

router = APIRouter()


@router.get("/categories")
async def get_categories():
    from app.marketplace.catalog import CATEGORIES
    return CATEGORIES


@router.get("/templates")
async def get_templates():
    """Lightweight metadata for the marketplace grid. No node/edge data."""
    from app.marketplace.catalog import list_templates
    return list_templates()


@router.get("/templates/{template_id}")
async def get_template_detail(template_id: str):
    """Full detail including a generated preview graph (read-only, not saved)."""
    from app.marketplace.catalog import get_template_meta, build_workflow_graph

    meta = get_template_meta(template_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Template not found")

    graph = build_workflow_graph(template_id)
    nodes, edges = graph if graph else ([], [])
    return {**meta, "preview_nodes": nodes, "preview_edges": edges}


@router.post("/templates/{template_id}/import", status_code=201)
async def import_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Creates a brand-new workflow in the user's workspace from a template.
    Never overwrites or modifies any existing workflow.
    """
    from app.marketplace.catalog import get_template_meta, build_workflow_graph

    meta = get_template_meta(template_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Template not found")

    graph = build_workflow_graph(template_id)
    if not graph:
        raise HTTPException(status_code=500, detail="Could not build template workflow")
    nodes, edges = graph

    workflow = Workflow(
        user_id=current_user.id,
        name=meta["name"],
        description=meta["description"],
        nodes=nodes,
        edges=edges,
        canvas_state={"x": 0, "y": 0, "zoom": 0.85},
        settings={},
        status="draft",
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)

    return {
        "id": str(workflow.id),
        "name": workflow.name,
        "description": workflow.description,
        "status": workflow.status,
        "nodes": workflow.nodes or [],
        "edges": workflow.edges or [],
        "canvas_state": workflow.canvas_state or {"x": 0, "y": 0, "zoom": 1},
        "settings": workflow.settings or {},
        "knowledge_base_id": None,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
    }
