"""Node catalog access: seeding from JSON files, and semantic-ish search.

Search here is lexical (token overlap over type/title/description/keywords).
In production this is pgvector cosine similarity over an `embedding` column —
the call-site contract (`search_nodes(query) → ranked NodeType rows`) is
identical, which is why the swap needs no agent changes.
"""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import NodeType

CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog"


async def seed_catalog(session: AsyncSession) -> int:
    """Upsert every JSON definition file. New node = new file or POST — no deploy."""
    count = 0
    for path in sorted(CATALOG_DIR.glob("*.json")):
        spec = json.loads(path.read_text())
        existing = await session.get(NodeType, spec["type"])
        if existing:
            for k, v in spec.items():
                setattr(existing, k, v)
        else:
            session.add(NodeType(**spec))
        count += 1
    await session.commit()
    return count


async def load_catalog(session: AsyncSession) -> dict[str, dict]:
    rows = (await session.execute(select(NodeType))).scalars().all()
    return {r.type: _row(r) for r in rows}


async def search_nodes(session: AsyncSession, query: str, limit: int = 5) -> list[dict]:
    catalog = await load_catalog(session)
    if not query:
        return list(catalog.values())[:limit]
    tokens = set(query.lower().replace(".", " ").replace("_", " ").split())

    def score(row: dict) -> int:
        hay = set(
            f"{row['type']} {row['title']} {row['description']}"
            .lower().replace(".", " ").replace("_", " ").split()
        ) | {k.lower() for k in row["keywords"]}
        return len(tokens & hay)

    ranked = sorted(catalog.values(), key=score, reverse=True)
    return [r for r in ranked if score(r) > 0][:limit] or ranked[:limit]


def _row(r: NodeType) -> dict:
    return {
        "type": r.type,
        "category": r.category,
        "title": r.title,
        "description": r.description,
        "keywords": r.keywords,
        "config_schema": r.config_schema,
        "input_ports": r.input_ports,
        "output_ports": r.output_ports,
    }
