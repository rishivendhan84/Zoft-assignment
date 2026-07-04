"""Operation-based workflow editing.

The agent never emits a whole graph — it emits a small list of operations.
`apply()` folds them over a *copy* of the current graph, so nothing persistent
is touched until the validator has passed and commit runs.
"""

import copy
from typing import Any

OPS = {"add_node", "remove_node", "connect", "disconnect", "set_config"}


class OperationError(Exception):
    """A structurally impossible operation (distinct from validation failures)."""


def empty_graph() -> dict:
    return {"nodes": [], "edges": []}


def _find_node(graph: dict, node_id: str) -> dict | None:
    return next((n for n in graph["nodes"] if n["id"] == node_id), None)


def apply(graph: dict, operations: list[dict[str, Any]]) -> dict:
    """Return a new graph with the operations applied. Never mutates the input."""
    g = copy.deepcopy(graph) if graph else empty_graph()

    for i, op in enumerate(operations):
        kind = op.get("op")
        if kind not in OPS:
            raise OperationError(f"operation {i}: unknown op '{kind}'")

        if kind == "add_node":
            if not op.get("id") or not op.get("type"):
                raise OperationError(f"operation {i}: add_node needs 'id' and 'type'")
            if _find_node(g, op["id"]):
                raise OperationError(f"operation {i}: node '{op['id']}' already exists")
            g["nodes"].append(
                {"id": op["id"], "type": op["type"], "config": op.get("config", {})}
            )

        elif kind == "remove_node":
            node = _find_node(g, op.get("id", ""))
            if not node:
                raise OperationError(f"operation {i}: node '{op.get('id')}' not found")
            g["nodes"].remove(node)
            g["edges"] = [
                e for e in g["edges"]
                if e["from"] != node["id"] and e["to"] != node["id"]
            ]

        elif kind == "connect":
            frm, to = op.get("from"), op.get("to")
            if not frm or not to:
                raise OperationError(f"operation {i}: connect needs 'from' and 'to'")
            edge = {"from": frm, "to": to}
            if op.get("port"):
                edge["port"] = op["port"]
            if any(e["from"] == frm and e["to"] == to for e in g["edges"]):
                raise OperationError(f"operation {i}: edge {frm}→{to} already exists")
            g["edges"].append(edge)

        elif kind == "disconnect":
            frm, to = op.get("from"), op.get("to")
            before = len(g["edges"])
            g["edges"] = [
                e for e in g["edges"] if not (e["from"] == frm and e["to"] == to)
            ]
            if len(g["edges"]) == before:
                raise OperationError(f"operation {i}: edge {frm}→{to} not found")

        elif kind == "set_config":
            node = _find_node(g, op.get("id", ""))
            if not node:
                raise OperationError(f"operation {i}: node '{op.get('id')}' not found")
            if not isinstance(op.get("config"), dict):
                raise OperationError(f"operation {i}: set_config needs a 'config' object")
            node["config"] = {**node.get("config", {}), **op["config"]}

    return g
