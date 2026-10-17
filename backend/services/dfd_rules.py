"""Rule-based validation for a DFD represented as the project's JSON structure.

This checks structural DFD conventions and inter-level balancing. It cannot prove
that a diagram accurately represents the real-world requirements; human review is
still needed for semantic correctness.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import re
from typing import Any


def _items(level: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = level.get(key, [])
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _node_id(node: dict[str, Any]) -> str:
    return _text(node.get("id"))


def _node_name(node: dict[str, Any]) -> str:
    for key in ("name", "label", "title"):
        value = _text(node.get(key))
        if value:
            return value
    return ""


def _flow_label(flow: dict[str, Any]) -> str:
    for key in ("name", "label", "data", "description", "data_flow"):
        value = _text(flow.get(key))
        if value:
            return value
    return ""


def _norm_label(value: str) -> str:
    return " ".join(value.casefold().split())


def _level_number(level: dict[str, Any]) -> int | None:
    value = level.get("level")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    match = re.search(r"\d+", _text(value))
    return int(match.group()) if match else None


def _add(
    violations: list[dict[str, Any]],
    *,
    rule_id: str,
    severity: str,
    level: int | None,
    message: str,
    element_id: str | None = None,
    suggestion: str = "",
) -> None:
    violations.append(
        {
            "rule_id": rule_id,
            "severity": severity,
            "level": level,
            "element_id": element_id,
            "message": message,
            "suggestion": suggestion,
        }
    )


def _make_node_map(level: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Return ID -> node type and duplicate IDs in this level."""
    node_types: dict[str, str] = {}
    duplicates: list[str] = []
    for key, kind in (
        ("external_entities", "entity"),
        ("processes", "process"),
        ("data_stores", "store"),
    ):
        for node in _items(level, key):
            node_id = _node_id(node)
            if not node_id:
                continue
            if node_id in node_types:
                duplicates.append(node_id)
            else:
                node_types[node_id] = kind
    return node_types, duplicates


def _flow_signatures_level0(level: dict[str, Any], main_process_id: str) -> Counter:
    """Flows across the context boundary: (direction, entity ID, label)."""
    types, _ = _make_node_map(level)
    result: Counter = Counter()
    for flow in _items(level, "data_flows"):
        source = _text(flow.get("source"))
        destination = _text(flow.get("destination"))
        label = _norm_label(_flow_label(flow))
        if not source or not destination or not label:
            continue
        if types.get(source) == "entity" and destination == main_process_id:
            result[("IN", source, label)] += 1
        elif source == main_process_id and types.get(destination) == "entity":
            result[("OUT", destination, label)] += 1
    return result


def _flow_signatures_level1(level: dict[str, Any]) -> Counter:
    """Flows across Level 1's outer boundary, replacing P0 with its processes."""
    types, _ = _make_node_map(level)
    process_ids = {n for n, t in types.items() if t == "process"}
    result: Counter = Counter()
    for flow in _items(level, "data_flows"):
        source = _text(flow.get("source"))
        destination = _text(flow.get("destination"))
        label = _norm_label(_flow_label(flow))
        if not source or not destination or not label:
            continue
        if types.get(source) == "entity" and destination in process_ids:
            result[("IN", source, label)] += 1
        elif source in process_ids and types.get(destination) == "entity":
            result[("OUT", destination, label)] += 1
    return result


def _process_boundary_signatures(
    level: dict[str, Any],
    process_id: str,
    node_types: dict[str, str],
) -> Counter:
    result: Counter = Counter()
    for flow in _items(level, "data_flows"):
        source = _text(flow.get("source"))
        destination = _text(flow.get("destination"))
        label = _norm_label(_flow_label(flow))
        if not label:
            continue
        if destination == process_id and source in node_types and source != process_id:
            result[("IN", source, label)] += 1
        elif source == process_id and destination in node_types and destination != process_id:
            result[("OUT", destination, label)] += 1
    return result


def _expanded_boundary_signatures(
    child_level: dict[str, Any],
    child_process_ids: set[str],
    parent_node_types: dict[str, str],
) -> Counter:
    """Child flows crossing its boundary, limited to nodes visible in parent level."""
    result: Counter = Counter()
    for flow in _items(child_level, "data_flows"):
        source = _text(flow.get("source"))
        destination = _text(flow.get("destination"))
        label = _norm_label(_flow_label(flow))
        if not label:
            continue
        if destination in child_process_ids and source in parent_node_types and source not in child_process_ids:
            result[("IN", source, label)] += 1
        elif source in child_process_ids and destination in parent_node_types and destination not in child_process_ids:
            result[("OUT", destination, label)] += 1
    return result


def audit_dfd(data: dict[str, Any]) -> dict[str, Any]:
    """Return a human-readable audit of DFD structural rules and balancing."""
    violations: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return {
            "status": "INVALID",
            "is_valid": False,
            "summary": "The supplied DFD must be a JSON object.",
            "checked_levels": [],
            "violation_count": 1,
            "violations": [{
                "rule_id": "JSON001", "severity": "error", "level": None,
                "element_id": None, "message": "The supplied DFD must be a JSON object.",
                "suggestion": "Pass the generated DFD JSON object to the audit endpoint.",
            }],
        }

    raw_levels = data.get("levels", [])
    if not isinstance(raw_levels, list) or not raw_levels:
        _add(violations, rule_id="LVL001", severity="error", level=None,
             message="No DFD levels were found.", suggestion="Provide a non-empty 'levels' array.")
        return _result(violations, [])

    levels = [lv for lv in raw_levels if isinstance(lv, dict)]
    levels.sort(key=lambda lv: _level_number(lv) if _level_number(lv) is not None else 999)
    by_number: dict[int, dict[str, Any]] = {}
    node_maps: dict[int, dict[str, str]] = {}
    for level in levels:
        number = _level_number(level)
        if number is None:
            _add(violations, rule_id="LVL002", severity="error", level=None,
                 message=f"Could not determine the level number from {level.get('level')!r}.",
                 suggestion="Use level values such as 0, 1, 2, or 3, or 'Level 0'.")
            continue
        if number in by_number:
            _add(violations, rule_id="LVL003", severity="error", level=number,
                 message=f"More than one level is labeled Level {number}.",
                 suggestion="Use one object per DFD level.")
        by_number[number] = level
        node_types, duplicate_ids = _make_node_map(level)
        node_maps[number] = node_types
        for duplicate in sorted(set(duplicate_ids)):
            _add(violations, rule_id="ID001", severity="error", level=number,
                 element_id=duplicate,
                 message=f"Node ID '{duplicate}' is used more than once in this level.",
                 suggestion="Give every entity, process, and data store a unique ID within the level.")

        # Required names and IDs.
        for key, kind in (("external_entities", "external entity"), ("processes", "process"), ("data_stores", "data store")):
            for index, node in enumerate(_items(level, key), start=1):
                node_id = _node_id(node)
                if not node_id:
                    _add(violations, rule_id="ID002", severity="error", level=number,
                         message=f"An {kind} is missing its ID (item {index}).",
                         suggestion="Assign a unique ID such as E1, P1, or D1.")
                if not _node_name(node):
                    _add(violations, rule_id="NAME001", severity="error", level=number,
                         element_id=node_id or None,
                         message=f"An {kind} has no descriptive name.",
                         suggestion="Give the element a short, meaningful name.")

        processes = _items(level, "processes")
        stores = _items(level, "data_stores")
        entities = _items(level, "external_entities")
        flows = _items(level, "data_flows")
        incoming: defaultdict[str, int] = defaultdict(int)
        outgoing: defaultdict[str, int] = defaultdict(int)
        connected: set[str] = set()

        # Level-specific checks.
        if number == 0:
            if len(processes) != 1:
                _add(violations, rule_id="L0-001", severity="error", level=0,
                     message=f"Level 0 must contain exactly one main process; found {len(processes)}.",
                     suggestion="Represent the entire system with a single process, normally P0.")
            if stores:
                _add(violations, rule_id="L0-002", severity="error", level=0,
                     message="Level 0 contains data stores, which are excluded from this project's context-diagram convention.",
                     suggestion="Move data stores to Level 1 or a deeper level.")
            if len(processes) == 1 and _node_id(processes[0]) != "P0":
                _add(violations, rule_id="L0-003", severity="warning", level=0,
                     element_id=_node_id(processes[0]) or None,
                     message="The sole Level 0 process is not identified as P0.",
                     suggestion="Use P0 for the context process to match this project's ID convention.")
            if len(processes) == 1 and processes[0].get("parent_process") not in (None, ""):
                _add(violations, rule_id="L0-004", severity="error", level=0,
                     element_id=_node_id(processes[0]),
                     message="The Level 0 context process must not have a parent process.",
                     suggestion="Set parent_process to null for P0.")

        # Validate every flow and count connections.
        for index, flow in enumerate(flows, start=1):
            flow_id = _text(flow.get("id")) or f"flow item {index}"
            source = _text(flow.get("source"))
            destination = _text(flow.get("destination"))
            label = _flow_label(flow)
            if not label:
                _add(violations, rule_id="FLOW001", severity="error", level=number,
                     element_id=flow_id,
                     message=f"Data flow '{flow_id}' has no label.",
                     suggestion="Add a short label describing the data being transferred.")
            if not source or not destination:
                _add(violations, rule_id="FLOW002", severity="error", level=number,
                     element_id=flow_id,
                     message=f"Data flow '{flow_id}' is missing a source or destination ID.",
                     suggestion="Use node IDs in source and destination, not element names.")
                continue
            if source not in node_maps.get(number, {}) or destination not in node_maps.get(number, {}):
                unknown = [node_id for node_id in (source, destination) if node_id not in node_maps.get(number, {})]
                _add(violations, rule_id="FLOW003", severity="error", level=number,
                     element_id=flow_id,
                     message=f"Data flow '{flow_id}' references unknown node ID(s): {', '.join(unknown)}.",
                     suggestion="Ensure source and destination reference IDs defined in the same level.")
                continue

            src_type = node_maps[number][source]
            dst_type = node_maps[number][destination]
            if src_type == "entity" and dst_type == "entity":
                _add(violations, rule_id="FLOW005", severity="error", level=number,
                     element_id=flow_id,
                     message="Two external entities are connected directly.",
                     suggestion="If this exchange belongs to the system, route it through a process.")
            if src_type == "store" and dst_type == "store":
                _add(violations, rule_id="FLOW006", severity="error", level=number,
                     element_id=flow_id,
                     message="Two data stores are connected directly.",
                     suggestion="Use a process to read, transform, and write the data.")
            if {src_type, dst_type} == {"entity", "store"}:
                _add(violations, rule_id="FLOW007", severity="error", level=number,
                     element_id=flow_id,
                     message="An external entity is connected directly to a data store.",
                     suggestion="A process must mediate access between external entities and data stores.")

            outgoing[source] += 1
            incoming[destination] += 1
            connected.add(source)
            connected.add(destination)

        # A process must have an input and an output; stores should be read and written.
        for process in processes:
            pid = _node_id(process)
            if not pid:
                continue
            if incoming[pid] == 0:
                _add(violations, rule_id="PROC001", severity="error", level=number,
                     element_id=pid,
                     message=f"Process '{pid}' has no incoming data flow (possible 'miracle' process).",
                     suggestion="Add a legitimate input or review whether this process belongs in the DFD.")
            if outgoing[pid] == 0:
                _add(violations, rule_id="PROC002", severity="error", level=number,
                     element_id=pid,
                     message=f"Process '{pid}' has no outgoing data flow (possible 'black hole' process).",
                     suggestion="Add a legitimate output or review whether this process belongs in the DFD.")

        for store in stores:
            sid = _node_id(store)
            if not sid:
                continue
            if incoming[sid] == 0:
                _add(violations, rule_id="STORE001", severity="warning", level=number,
                     element_id=sid,
                     message=f"Data store '{sid}' has no incoming flow.",
                     suggestion="Check whether the store should receive data from a process.")
            if outgoing[sid] == 0:
                _add(violations, rule_id="STORE002", severity="warning", level=number,
                     element_id=sid,
                     message=f"Data store '{sid}' has no outgoing flow.",
                     suggestion="Check whether any process reads data from this store.")

        for entity in entities:
            eid = _node_id(entity)
            if eid and eid not in connected:
                _add(violations, rule_id="ENTITY001", severity="warning", level=number,
                     element_id=eid,
                     message=f"External entity '{eid}' has no data-flow connection.",
                     suggestion="Connect it to a relevant process or remove it if it is outside the diagram's scope.")

        # Check the process-ID hierarchy and parent_process references.
        for process in processes:
            pid = _node_id(process)
            if not pid:
                continue
            parent = _text(process.get("parent_process"))
            if number == 1:
                if parent != "P0":
                    _add(violations, rule_id="HIER001", severity="error", level=1,
                         element_id=pid,
                         message=f"Level 1 process '{pid}' should have parent_process 'P0'; found {parent or 'missing'}.",
                         suggestion="Set parent_process to P0 for Level 1 processes.")
                if not re.fullmatch(r"P\d+", pid):
                    _add(violations, rule_id="HIER002", severity="warning", level=1,
                         element_id=pid,
                         message=f"Level 1 process ID '{pid}' does not follow the expected P1, P2, ... format.",
                         suggestion="Use a whole-number process ID such as P1 or P2.")
            elif number >= 2:
                expected_parent = pid.rsplit(".", 1)[0] if "." in pid else ""
                if not expected_parent or not re.fullmatch(r"P\d+(?:\.\d+){" + str(number - 2) + r"}", expected_parent):
                    example_id = "P3" + "".join(".1" for _ in range(number - 1))
                    _add(violations, rule_id="HIER003", severity="error", level=number,
                         element_id=pid,
                         message=f"Process ID '{pid}' does not follow the expected Level {number} hierarchy.",
                         suggestion=f"Use a hierarchical ID such as {example_id} for Level {number}.")
                if parent != expected_parent:
                    _add(violations, rule_id="HIER004", severity="error", level=number,
                         element_id=pid,
                         message=f"Process '{pid}' should reference parent_process '{expected_parent or 'a valid parent'}'; found {parent or 'missing'}.",
                         suggestion="Set parent_process to the process ID one level above it.")
                previous_process_ids = {
                    _node_id(p) for p in _items(by_number.get(number - 1, {}), "processes")
                }
                if parent and parent not in previous_process_ids:
                    _add(violations, rule_id="HIER005", severity="error", level=number,
                         element_id=pid,
                         message=f"Parent process '{parent}' for '{pid}' does not exist in Level {number - 1}.",
                         suggestion="Check the parent ID against the previous level's process IDs.")

    # Level 0 -> Level 1 balancing. This is a warning because label granularity may vary.
    if 0 in by_number and 1 in by_number:
        l0_processes = _items(by_number[0], "processes")
        if len(l0_processes) == 1:
            p0 = _node_id(l0_processes[0])
            parent_signatures = _flow_signatures_level0(by_number[0], p0)
            child_signatures = _flow_signatures_level1(by_number[1])
            missing = parent_signatures - child_signatures
            added = child_signatures - parent_signatures
            if missing or added:
                detail = []
                if missing:
                    detail.append(f"missing from Level 1: {_format_signatures(missing)}")
                if added:
                    detail.append(f"not shown at Level 0: {_format_signatures(added)}")
                _add(violations, rule_id="BAL001", severity="warning", level=1,
                     message="Level 0 and Level 1 external data flows may be unbalanced; " + "; ".join(detail) + ".",
                     suggestion="Compare external entity IDs, flow directions, and labels across the two levels. Equivalent flows should retain the same meaning and normally the same label.")

    # Parent-process balancing for each deeper level.
    level_numbers = sorted(by_number)
    for child_number in level_numbers:
        if child_number < 2:
            continue
        parent_number = child_number - 1
        if parent_number not in by_number:
            continue
        parent_level = by_number[parent_number]
        child_level = by_number[child_number]
        parent_node_types = node_maps.get(parent_number, {})
        child_processes = _items(child_level, "processes")
        child_ids_by_parent: defaultdict[str, set[str]] = defaultdict(set)
        for process in child_processes:
            parent_id = _text(process.get("parent_process"))
            pid = _node_id(process)
            if parent_id and pid:
                child_ids_by_parent[parent_id].add(pid)

        for parent_process_id, child_ids in child_ids_by_parent.items():
            # Compare only if parent process exists in the parent-level model.
            if parent_process_id not in parent_node_types or parent_node_types[parent_process_id] != "process":
                continue
            parent_signatures = _process_boundary_signatures(parent_level, parent_process_id, parent_node_types)
            child_signatures = _expanded_boundary_signatures(child_level, child_ids, parent_node_types)
            missing = parent_signatures - child_signatures
            added = child_signatures - parent_signatures
            if missing or added:
                detail = []
                if missing:
                    detail.append(f"parent flows not represented in Level {child_number}: {_format_signatures(missing)}")
                if added:
                    detail.append(f"new boundary flows not present on parent process: {_format_signatures(added)}")
                _add(violations, rule_id="BAL002", severity="warning", level=child_number,
                     element_id=parent_process_id,
                     message=f"The decomposition of '{parent_process_id}' may be unbalanced; " + "; ".join(detail) + ".",
                     suggestion="Make sure the child diagram preserves the parent's incoming and outgoing boundary flows. Internal flows and newly introduced internal stores do not need to appear in the parent diagram.")

    checked_levels = sorted(by_number)
    return _result(violations, checked_levels)


def _format_signatures(signatures: Counter) -> str:
    parts: list[str] = []
    for (direction, endpoint, label), count in sorted(signatures.items()):
        arrow = "into expanded process" if direction == "IN" else "out of expanded process"
        parts.append(f"{count} × {label!r} ({endpoint}, {arrow})")
    return ", ".join(parts[:8]) + (", …" if len(parts) > 8 else "")


def _result(violations: list[dict[str, Any]], checked_levels: list[int]) -> dict[str, Any]:
    errors = sum(v["severity"] == "error" for v in violations)
    warnings = sum(v["severity"] == "warning" for v in violations)
    if errors:
        status = "INVALID"
    elif warnings:
        status = "NEEDS_REVIEW"
    else:
        status = "VALID"
    return {
        "status": status,
        "is_valid": errors == 0 and warnings == 0,
        "structurally_valid": errors == 0,
        "summary": (
            "No rule violations were detected. This does not prove semantic correctness."
            if not violations else
            f"Found {errors} error(s) and {warnings} warning(s). Review the findings below."
        ),
        "checked_levels": checked_levels,
        "violation_count": len(violations),
        "error_count": errors,
        "warning_count": warnings,
        "violations": violations,
    }
