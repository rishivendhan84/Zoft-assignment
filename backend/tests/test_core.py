"""Unit tests for the deterministic core: operations, validator, diff."""

import pytest

from app.core import operations as ops
from app.core.diff import diff_graphs
from app.core.validator import validate_graph

CATALOG = {
    "stripe.payment_received": {
        "type": "stripe.payment_received", "category": "trigger",
        "title": "Stripe", "keywords": ["stripe"],
        "config_schema": {"type": "object", "additionalProperties": False},
        "input_ports": [], "output_ports": ["out"],
    },
    "slack.send_message": {
        "type": "slack.send_message", "category": "action",
        "title": "Slack", "keywords": ["slack"],
        "config_schema": {
            "type": "object",
            "properties": {"channel": {"type": "string", "pattern": "^#"},
                           "text": {"type": "string", "minLength": 1}},
            "required": ["channel", "text"], "additionalProperties": False,
        },
        "input_ports": ["in"], "output_ports": ["out"],
    },
    "logic.filter": {
        "type": "logic.filter", "category": "logic",
        "title": "Filter", "keywords": ["filter"],
        "config_schema": {"type": "object",
                          "properties": {"conditions": {"type": "array"}},
                          "required": ["conditions"]},
        "input_ports": ["in"], "output_ports": ["true", "false"],
    },
}


def make_graph():
    return ops.apply(ops.empty_graph(), [
        {"op": "add_node", "id": "n1", "type": "stripe.payment_received"},
        {"op": "add_node", "id": "n2", "type": "slack.send_message",
         "config": {"channel": "#sales", "text": "hi"}},
        {"op": "connect", "from": "n1", "to": "n2"},
    ])


class TestOperations:
    def test_apply_never_mutates_input(self):
        g = make_graph()
        snapshot = str(g)
        ops.apply(g, [{"op": "remove_node", "id": "n2"}])
        assert str(g) == snapshot

    def test_remove_node_drops_its_edges(self):
        g = ops.apply(make_graph(), [{"op": "remove_node", "id": "n2"}])
        assert g["edges"] == []

    def test_set_config_merges(self):
        g = ops.apply(make_graph(), [
            {"op": "set_config", "id": "n2", "config": {"channel": "#ops"}}])
        n2 = next(n for n in g["nodes"] if n["id"] == "n2")
        assert n2["config"] == {"channel": "#ops", "text": "hi"}

    @pytest.mark.parametrize("bad", [
        {"op": "teleport", "id": "n1"},
        {"op": "add_node", "id": "n1", "type": "x"},          # duplicate id
        {"op": "remove_node", "id": "ghost"},
        {"op": "connect", "from": "n1", "to": "n2"},          # duplicate edge
        {"op": "disconnect", "from": "n2", "to": "n1"},       # no such edge
    ])
    def test_impossible_operations_raise(self, bad):
        with pytest.raises(ops.OperationError):
            ops.apply(make_graph(), [bad])


class TestValidator:
    def test_valid_graph_passes(self):
        assert validate_graph(make_graph(), CATALOG).ok

    def test_hallucinated_node_rejected_with_hint(self):
        g = ops.apply(make_graph(), [
            {"op": "remove_node", "id": "n2"},
            {"op": "add_node", "id": "n3", "type": "sms.send_text",
             "config": {}},
            {"op": "connect", "from": "n1", "to": "n3"},
        ])
        result = validate_graph(g, CATALOG)
        codes = [e.code for e in result.errors]
        assert "unknown_node_type" in codes
        assert "Did you mean" in result.errors[0].message

    def test_missing_required_config(self):
        g = ops.apply(make_graph(), [
            {"op": "add_node", "id": "n3", "type": "slack.send_message"},
            {"op": "connect", "from": "n1", "to": "n3"},
        ])
        result = validate_graph(g, CATALOG)
        assert any(e.code == "invalid_config" and e.node == "n3"
                   for e in result.errors)

    def test_dangling_edge_and_orphan(self):
        g = make_graph()
        g["edges"].append({"from": "n1", "to": "ghost"})
        result = validate_graph(g, CATALOG)
        assert any(e.code == "dangling_edge" for e in result.errors)

    def test_multiple_triggers_rejected(self):
        g = make_graph()
        g["nodes"].append({"id": "n9", "type": "stripe.payment_received",
                           "config": {}})
        result = validate_graph(g, CATALOG)
        assert any(e.code == "multiple_triggers" for e in result.errors)

    def test_invalid_port_rejected(self):
        g = make_graph()
        g["edges"][0]["port"] = "maybe"
        result = validate_graph(g, CATALOG)
        assert any(e.code == "invalid_port" for e in result.errors)

    def test_cycle_rejected(self):
        g = make_graph()
        g["nodes"].append({"id": "n3", "type": "logic.filter",
                           "config": {"conditions": []}})
        g["edges"].append({"from": "n2", "to": "n3"})
        g["edges"].append({"from": "n3", "to": "n2"})
        result = validate_graph(g, CATALOG)
        assert any(e.code == "cycle" for e in result.errors)

    def test_edge_into_trigger_rejected(self):
        g = make_graph()
        g["edges"].append({"from": "n2", "to": "n1"})
        result = validate_graph(g, CATALOG)
        assert any(e.code == "invalid_edge" for e in result.errors)

    def test_multi_output_edge_must_name_a_port(self):
        g = ops.apply(make_graph(), [
            {"op": "disconnect", "from": "n1", "to": "n2"},
            {"op": "add_node", "id": "n3", "type": "logic.filter",
             "config": {"conditions": []}},
            {"op": "connect", "from": "n1", "to": "n3"},
            {"op": "connect", "from": "n3", "to": "n2"},  # no port → ambiguous
        ])
        result = validate_graph(g, CATALOG)
        assert any(e.code == "ambiguous_port" for e in result.errors)
        g["edges"] = [e if e["from"] != "n3" else {**e, "port": "true"}
                      for e in g["edges"]]
        assert validate_graph(g, CATALOG).ok

    def test_broken_catalog_schema_is_an_error_not_a_crash(self):
        catalog = {**CATALOG, "bad.node": {
            "type": "bad.node", "category": "action", "title": "Bad",
            "keywords": [], "config_schema": {"type": "objekt"},  # invalid
            "input_ports": ["in"], "output_ports": ["out"]}}
        g = ops.apply(make_graph(), [
            {"op": "add_node", "id": "n3", "type": "bad.node"},
            {"op": "connect", "from": "n1", "to": "n3"},
        ])
        result = validate_graph(g, catalog)
        assert any(e.code == "broken_catalog_schema" for e in result.errors)


class TestDiff:
    def test_diff_roundtrip(self):
        old = make_graph()
        new = ops.apply(old, [
            {"op": "disconnect", "from": "n1", "to": "n2"},
            {"op": "add_node", "id": "n3", "type": "logic.filter",
             "config": {"conditions": [{"field": "amount", "op": ">", "value": 500}]}},
            {"op": "connect", "from": "n1", "to": "n3"},
            {"op": "connect", "from": "n3", "to": "n2", "port": "true"},
        ])
        # applying the structural diff to `old` must reproduce `new`
        rebuilt = ops.apply(old, diff_graphs(old, new))
        assert {n["id"] for n in rebuilt["nodes"]} == {n["id"] for n in new["nodes"]}
        assert sorted(str(e) for e in rebuilt["edges"]) == \
               sorted(str(e) for e in new["edges"])

    def test_reused_id_with_new_type_is_replace_not_config_edit(self):
        old = make_graph()
        new = make_graph()
        new["nodes"][1] = {"id": "n2", "type": "logic.filter",
                           "config": {"conditions": []}}
        d = diff_graphs(old, new)
        kinds = [o["op"] for o in d]
        assert "remove_node" in kinds and "add_node" in kinds
        assert "set_config" not in kinds
        rebuilt = ops.apply(old, d)
        assert next(n for n in rebuilt["nodes"] if n["id"] == "n2")["type"] \
               == "logic.filter"
        assert rebuilt["edges"] == new["edges"]  # surviving edge re-issued

    def test_config_change_becomes_set_config(self):
        old, new = make_graph(), make_graph()
        new["nodes"][1]["config"]["channel"] = "#ops"
        d = diff_graphs(old, new)
        assert d == [{"op": "set_config", "id": "n2",
                      "config": {"channel": "#ops", "text": "hi"}}]

    def test_removed_config_key_round_trips_via_null(self):
        old, new = make_graph(), make_graph()
        del new["nodes"][1]["config"]["text"]
        d = diff_graphs(old, new)
        assert d == [{"op": "set_config", "id": "n2",
                      "config": {"channel": "#sales", "text": None}}]
        rebuilt = ops.apply(old, d)
        assert rebuilt["nodes"][1]["config"] == {"channel": "#sales"}
