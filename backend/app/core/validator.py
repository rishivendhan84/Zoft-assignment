"""Deterministic validation — the gate between the AI and persistence.

Pure code. Takes the candidate graph (already produced by applying the
proposed operations to a copy) plus the node catalog, and returns a list of
errors. Empty list ⇒ safe to commit. The LLM is never consulted here.
"""

from dataclasses import dataclass, field

import jsonschema


@dataclass
class ValidationError:
    node: str | None
    code: str
    message: str

    def to_dict(self) -> dict:
        return {"node": self.node, "code": self.code, "message": self.message}


@dataclass
class ValidationResult:
    errors: list[ValidationError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_graph(graph: dict, catalog: dict[str, dict]) -> ValidationResult:
    """catalog: node type → catalog row (config_schema, ports, category)."""
    errors: list[ValidationError] = []
    nodes = {n["id"]: n for n in graph.get("nodes", [])}

    # 1. Every node type must exist in the catalog (kills hallucinated nodes).
    for node in graph.get("nodes", []):
        spec = catalog.get(node["type"])
        if spec is None:
            near = _nearest_types(node["type"], catalog)
            hint = f" Did you mean: {', '.join(near)}?" if near else ""
            errors.append(ValidationError(
                node["id"], "unknown_node_type",
                f"Node type '{node['type']}' does not exist in the catalog.{hint}",
            ))
            continue

        # 2. Config must satisfy the type's JSON Schema. A broken schema in the
        # catalog (data, not code — so it can be wrong) must surface as a
        # validation error, never as a crashed run.
        try:
            validator = jsonschema.Draft202012Validator(spec["config_schema"])
            config_errors = sorted(
                validator.iter_errors(node.get("config", {})), key=str)
        except Exception as e:
            errors.append(ValidationError(
                node["id"], "broken_catalog_schema",
                f"config_schema for '{node['type']}' is not a valid JSON Schema: {e}",
            ))
            continue
        for err in config_errors:
            path = ".".join(str(p) for p in err.absolute_path) or "config"
            errors.append(ValidationError(
                node["id"], "invalid_config", f"{path}: {err.message}",
            ))

    # 3. Edges must reference existing nodes and legal ports.
    for edge in graph.get("edges", []):
        src, dst = nodes.get(edge["from"]), nodes.get(edge["to"])
        if src is None:
            errors.append(ValidationError(
                None, "dangling_edge", f"Edge source '{edge['from']}' does not exist.",
            ))
        if dst is None:
            errors.append(ValidationError(
                None, "dangling_edge", f"Edge target '{edge['to']}' does not exist.",
            ))
        if src and dst:
            src_spec, dst_spec = catalog.get(src["type"]), catalog.get(dst["type"])
            port = edge.get("port")
            if src_spec and port and port not in src_spec["output_ports"]:
                errors.append(ValidationError(
                    src["id"], "invalid_port",
                    f"'{src['type']}' has no output port '{port}' "
                    f"(available: {src_spec['output_ports']}).",
                ))
            if src_spec and not src_spec["output_ports"]:
                errors.append(ValidationError(
                    src["id"], "invalid_edge",
                    f"'{src['type']}' has no output ports and cannot start an edge.",
                ))
            if src_spec and len(src_spec["output_ports"]) > 1 and not port:
                errors.append(ValidationError(
                    src["id"], "ambiguous_port",
                    f"'{src['type']}' has multiple output ports "
                    f"({src_spec['output_ports']}); the edge to "
                    f"'{edge['to']}' must name one.",
                ))
            if dst_spec and not dst_spec["input_ports"]:
                errors.append(ValidationError(
                    dst["id"], "invalid_edge",
                    f"'{dst['type']}' is a trigger and cannot receive an edge.",
                ))

    # 4. Graph-level rules.
    if graph.get("nodes"):
        triggers = [
            n for n in graph["nodes"]
            if catalog.get(n["type"], {}).get("category") == "trigger"
        ]
        if not triggers:
            errors.append(ValidationError(
                None, "no_trigger", "Workflow needs exactly one trigger node.",
            ))
        elif len(triggers) > 1:
            errors.append(ValidationError(
                None, "multiple_triggers",
                f"Workflow has {len(triggers)} triggers; only one is allowed.",
            ))

        connected = {e["from"] for e in graph["edges"]} | {e["to"] for e in graph["edges"]}
        for n in graph["nodes"]:
            spec = catalog.get(n["type"])
            if spec and spec["input_ports"] and n["id"] not in {
                e["to"] for e in graph["edges"]
            }:
                errors.append(ValidationError(
                    n["id"], "unreachable_node",
                    f"'{n['type']}' node '{n['id']}' has no incoming edge.",
                ))
            if len(graph["nodes"]) > 1 and n["id"] not in connected:
                errors.append(ValidationError(
                    n["id"], "orphan_node",
                    f"Node '{n['id']}' is not connected to the workflow.",
                ))

        if _has_cycle(graph):
            errors.append(ValidationError(
                None, "cycle", "Workflow graph contains a cycle.",
            ))

    # De-duplicate (orphan + unreachable can overlap in message intent)
    seen: set[tuple] = set()
    unique = []
    for e in errors:
        key = (e.node, e.code, e.message)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return ValidationResult(unique)


def _has_cycle(graph: dict) -> bool:
    adj: dict[str, list[str]] = {}
    for e in graph.get("edges", []):
        adj.setdefault(e["from"], []).append(e["to"])
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n["id"]: WHITE for n in graph.get("nodes", [])}

    def dfs(u: str) -> bool:
        color[u] = GRAY
        for v in adj.get(u, []):
            if color.get(v) == GRAY:
                return True
            if color.get(v) == WHITE and dfs(v):
                return True
        color[u] = BLACK
        return False

    return any(color[n] == WHITE and dfs(n) for n in list(color))


def _nearest_types(unknown: str, catalog: dict[str, dict], limit: int = 3) -> list[str]:
    """Cheap lexical proximity for repair-loop hints ('valid types near X')."""
    tokens = set(unknown.lower().replace(".", " ").replace("_", " ").split())

    def score(t: str) -> int:
        row = catalog[t]
        hay = set(
            (t + " " + row.get("title", "")).lower()
            .replace(".", " ").replace("_", " ").split()
        ) | {k.lower() for k in row.get("keywords", [])}
        return len(tokens & hay)

    ranked = sorted(catalog, key=score, reverse=True)
    return [t for t in ranked[:limit] if score(t) > 0] or list(catalog)[:limit]
