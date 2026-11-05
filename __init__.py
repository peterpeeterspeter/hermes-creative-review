"""Creative Review — agent-half registration.

Registers the seven Creative Review tools and the bundled workflow skill. The
Desktop half lives beside this file (``desktop/plugin.js``) and the backend
under ``dashboard/``; together they are one installable package.
"""
from __future__ import annotations

import logging
from pathlib import Path

from . import schemas, tools

logger = logging.getLogger(__name__)

_TOOL_HANDLERS = (
    (schemas.CREATE_BOARD, tools.create_board),
    (schemas.LIST_BOARDS, tools.list_boards),
    (schemas.ADD_IMAGE, tools.add_image),
    (schemas.GET_BOARD, tools.get_board),
    (schemas.REVISION_BRIEF, tools.revision_brief),
    (schemas.APPROVE, tools.approve),
    (schemas.EXPORT, tools.export_board),
)


def _register_skills(ctx) -> None:
    skills_dir = Path(__file__).parent / "skills"
    if not skills_dir.is_dir():
        return
    for child in sorted(skills_dir.iterdir()):
        skill_md = child / "SKILL.md"
        if child.is_dir() and skill_md.exists():
            try:
                ctx.register_skill(child.name, skill_md)
            except Exception:  # noqa: BLE001
                logger.warning("creative-review: could not register skill %s", child.name,
                               exc_info=True)


def register(ctx) -> None:
    """Wire schemas to handlers and bundle the workflow skill."""
    for schema, handler in _TOOL_HANDLERS:
        ctx.register_tool(
            name=schema["name"],
            toolset=schemas.TOOLSET,
            schema=schema,
            handler=handler,
        )
    _register_skills(ctx)