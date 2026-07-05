"""Structural diff between two workflow graphs, expressed as operations.

Works for ANY pair of versions (not just parent→child), so the diff endpoint
never depends on the stored operation log being contiguous. Invariant (tested):
applying the returned operations to `old` reproduces `new`.
"""


def diff_graphs(old: dict, new: dict) -> list[dict]:
    old_nodes = {n["id"]: n for n in (old or {}).get("nodes", [])}
    new_nodes = {n["id"]: n for n in (new or {}).get("nodes", [])}
    old_edges = {_ekey(e): e for e in (old or {}).get("edges", [])}
    new_edges = {_ekey(e): e for e in (new or {}).get("edges", [])}

    # An id reused for a different node type across versions is a replacement,
    # not a config edit. Its surviving edges must be re-issued because
    # remove_node drops them.
    replaced = {
        nid for nid in old_nodes.keys() & new_nodes.keys()
        if old_nodes[nid]["type"] != new_nodes[nid]["type"]
    }

    def touches_replaced(ekey: tuple) -> bool:
        return ekey[0] in replaced or ekey[1] in replaced

    ops: list[dict] = []

    for eid, e in old_edges.items():
        if eid not in new_edges and not touches_replaced(eid):
            ops.append({"op": "disconnect", "from": e["from"], "to": e["to"]})

    for nid in old_nodes:
        if nid not in new_nodes or nid in replaced:
            ops.append({"op": "remove_node", "id": nid})  # implicitly drops edges

    for nid, n in new_nodes.items():
        if nid not in old_nodes or nid in replaced:
            ops.append(
                {"op": "add_node", "id": nid, "type": n["type"],
                 "config": n.get("config", {})}
            )
        elif n.get("config", {}) != old_nodes[nid].get("config", {}):
            # null-out keys that disappeared so apply() round-trips exactly
            payload = dict(n.get("config", {}))
            for key in old_nodes[nid].get("config", {}):
                if key not in payload:
                    payload[key] = None
            ops.append({"op": "set_config", "id": nid, "config": payload})

    for eid, e in new_edges.items():
        if eid not in old_edges or touches_replaced(eid):
            op = {"op": "connect", "from": e["from"], "to": e["to"]}
            if e.get("port"):
                op["port"] = e["port"]
            ops.append(op)

    return ops


def _ekey(e: dict) -> tuple:
    return (e["from"], e["to"], e.get("port"))
