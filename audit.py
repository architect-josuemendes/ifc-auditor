"""
ifc-auditor — Validate IFC files against configurable BEP/EIR rules.

Usage:
    python audit.py examples/sample.ifc --rules rules.yaml --output report.html

Output:
    - report.html — navigable HTML audit report
    - Exit code 0 if all CRITICAL rules pass, 1 if any CRITICAL fails

Author: Josue Mendes
License: MIT
"""
from __future__ import annotations

import re
import sys
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import yaml
from jinja2 import Environment, FileSystemLoader
import ifcopenshell
import ifcopenshell.util.element


# ============================================================
# RESULT TYPES
# ============================================================

@dataclass
class CheckResult:
    """Result of a single rule check."""
    rule_id: str
    rule_name: str
    severity: str       # critical | major | minor
    status: str         # pass | fail | warn
    total: int = 0      # elements checked
    passed: int = 0     # elements passing
    failed: int = 0     # elements failing
    coverage: float = 0.0  # passed / total ratio
    message: str = ""
    failing_elements: list[dict] = field(default_factory=list)

    @property
    def coverage_pct(self) -> str:
        return f"{self.coverage * 100:.0f}%"


# ============================================================
# CHECK IMPLEMENTATIONS
# ============================================================

def check_regex(model, params: dict) -> CheckResult:
    """Check that a target value matches a regex pattern."""
    target = params["target"]
    pattern = params["pattern"]

    if "." in target:
        ifc_class, attr = target.split(".", 1)
        entities = model.by_type(ifc_class)
        if not entities:
            return _result("fail", 0, 0, 0, "No entities of target class found")
        entity = entities[0]
        value = getattr(entity, attr, None)
    else:
        value = None

    if value and re.match(pattern, str(value)):
        return _result("pass", 1, 1, 0, f"'{value}' matches pattern")
    return _result(
        "fail", 1, 0, 1,
        f"'{value}' does not match required pattern: {pattern}",
        [{"id": entity.GlobalId, "name": str(value or '<empty>'),
          "reason": "Does not match ISO 19650 naming convention"}]
    )


def check_schema(model, params: dict) -> CheckResult:
    """Check that the IFC schema version is in the allowed list."""
    allowed = params["allowed"]
    actual = model.schema
    if actual in allowed:
        return _result("pass", 1, 1, 0, f"Schema {actual} is approved")
    return _result(
        "fail", 1, 0, 1,
        f"Schema '{actual}' is not in approved list: {allowed}"
    )


def check_count_min(model, params: dict) -> CheckResult:
    """Check that at least N entities of a given class exist."""
    ifc_class = params["ifc_class"]
    minimum = params["min"]
    count = len(model.by_type(ifc_class))
    if count >= minimum:
        return _result("pass", count, count, 0,
                       f"{count} × {ifc_class} (≥ {minimum} required)")
    return _result("fail", count, count, minimum - count,
                   f"Only {count} × {ifc_class} found, ≥ {minimum} required")


def check_property_required(model, params: dict) -> CheckResult:
    """Check that all elements of an IFC class have a specified property."""
    ifc_class = params["ifc_class"]
    pset_name = params["pset"]
    property_name = params["property"]
    elements = model.by_type(ifc_class)
    total = len(elements)
    if total == 0:
        return _result("warn", 0, 0, 0, f"No {ifc_class} elements found")

    failing = []
    passed = 0
    for el in elements:
        psets = ifcopenshell.util.element.get_psets(el) or {}
        pset = psets.get(pset_name, {})
        value = pset.get(property_name)
        if value is not None and value != "":
            passed += 1
        else:
            failing.append({
                "id": el.GlobalId,
                "name": el.Name or "<unnamed>",
                "reason": f"Missing {pset_name}.{property_name}"
            })

    if not failing:
        return _result("pass", total, total, 0,
                       f"All {total} {ifc_class}s have {pset_name}.{property_name}")
    return _result(
        "fail", total, passed, len(failing),
        f"{len(failing)}/{total} {ifc_class}s missing {pset_name}.{property_name}",
        failing[:50]   # cap shown failures to 50
    )


def check_material_required(model, params: dict) -> CheckResult:
    """Check that all elements of an IFC class have a material assignment."""
    ifc_class = params["ifc_class"]
    elements = model.by_type(ifc_class)
    total = len(elements)
    if total == 0:
        return _result("warn", 0, 0, 0, f"No {ifc_class} elements found")

    failing = []
    passed = 0
    for el in elements:
        mat = ifcopenshell.util.element.get_material(el)
        if mat is not None:
            passed += 1
        else:
            failing.append({
                "id": el.GlobalId,
                "name": el.Name or "<unnamed>",
                "reason": "No material assigned"
            })

    if not failing:
        return _result("pass", total, total, 0,
                       f"All {total} {ifc_class}s have material assignment")
    return _result(
        "fail", total, passed, len(failing),
        f"{len(failing)}/{total} {ifc_class}s missing material",
        failing[:50]
    )


def check_spatial_orphans(model, params: dict) -> CheckResult:
    """Check that all physical elements are contained in a spatial structure."""
    classes = params["element_classes"]
    all_elements = []
    for cls in classes:
        all_elements.extend(model.by_type(cls))
    total = len(all_elements)

    failing = []
    for el in all_elements:
        # Walk up ContainedInStructure
        container = ifcopenshell.util.element.get_container(el)
        if container is None:
            failing.append({
                "id": el.GlobalId,
                "name": el.Name or "<unnamed>",
                "reason": f"{el.is_a()} not assigned to a spatial structure"
            })

    passed = total - len(failing)
    if not failing:
        return _result("pass", total, total, 0,
                       f"All {total} elements properly assigned to spatial structure")
    return _result(
        "fail", total, passed, len(failing),
        f"{len(failing)} orphan elements (not in spatial structure)",
        failing[:50]
    )


def check_unique_guids(model, params: dict) -> CheckResult:
    """Check that all GlobalIds are unique across the model."""
    seen = {}
    duplicates = []
    for el in model.by_type("IfcRoot"):
        gid = el.GlobalId
        if gid in seen:
            duplicates.append({
                "id": gid, "name": el.Name or "<unnamed>",
                "reason": f"Duplicate of {seen[gid].is_a()} {seen[gid].id()}"
            })
        else:
            seen[gid] = el
    total = len(seen)
    if not duplicates:
        return _result("pass", total, total, 0, f"All {total} GlobalIds unique")
    return _result(
        "fail", total, total - len(duplicates), len(duplicates),
        f"{len(duplicates)} duplicate GlobalIds found", duplicates[:50]
    )


# Helper
def _result(status, total, passed, failed, message, failing=None):
    return {
        "status": status,
        "total": total,
        "passed": passed,
        "failed": failed,
        "coverage": passed / total if total > 0 else 1.0,
        "message": message,
        "failing_elements": failing or [],
    }


# Registry of check types
CHECKS = {
    "regex":             check_regex,
    "schema":            check_schema,
    "count_min":         check_count_min,
    "property_required": check_property_required,
    "material_required": check_material_required,
    "spatial_orphans":   check_spatial_orphans,
    "unique_guids":      check_unique_guids,
}


# ============================================================
# MAIN AUDIT RUNNER
# ============================================================

def run_audit(ifc_path: str, rules_path: str) -> dict:
    """Execute all rules against the IFC and return structured results."""
    model = ifcopenshell.open(ifc_path)
    with open(rules_path) as f:
        config = yaml.safe_load(f)

    results = []
    for rule in config["rules"]:
        check_type = rule["check"]["type"]
        check_fn = CHECKS.get(check_type)
        if check_fn is None:
            results.append(CheckResult(
                rule_id=rule["id"], rule_name=rule["name"],
                severity=rule["severity"], status="warn",
                message=f"Unknown check type: {check_type}"
            ))
            continue
        raw = check_fn(model, rule["check"])
        results.append(CheckResult(
            rule_id=rule["id"],
            rule_name=rule["name"],
            severity=rule["severity"],
            **raw,
        ))

    # Summary
    total_rules = len(results)
    passed_rules = sum(1 for r in results if r.status == "pass")
    failed_critical = sum(1 for r in results
                          if r.severity == "critical" and r.status == "fail")
    failed_major = sum(1 for r in results
                       if r.severity == "major" and r.status == "fail")
    failed_minor = sum(1 for r in results
                       if r.severity == "minor" and r.status == "fail")

    return {
        "project_info": config.get("project_info", {}),
        "ifc_file": os.path.basename(ifc_path),
        "ifc_schema": model.schema,
        "ifc_size_kb": os.path.getsize(ifc_path) / 1024,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "results": results,
        "summary": {
            "total_rules":    total_rules,
            "passed_rules":   passed_rules,
            "pass_rate":      passed_rules / total_rules if total_rules else 0,
            "failed_critical": failed_critical,
            "failed_major":    failed_major,
            "failed_minor":    failed_minor,
            "overall_status": "PASS" if failed_critical == 0 else "FAIL",
        },
    }


def render_report(audit: dict, template_dir: str, output: str):
    """Render HTML report using Jinja2."""
    env = Environment(loader=FileSystemLoader(template_dir),
                      trim_blocks=True, lstrip_blocks=True)
    template = env.get_template("report.html.j2")
    html = template.render(audit=audit)
    with open(output, "w", encoding="utf-8") as f:
        f.write(html)


# ============================================================
# CLI
# ============================================================

@click.command()
@click.argument("ifc_file", type=click.Path(exists=True))
@click.option("--rules", "-r", default="rules.yaml",
              type=click.Path(exists=True),
              help="Path to rules YAML file")
@click.option("--output", "-o", default="report.html",
              help="Output HTML report path")
@click.option("--templates", "-t", default="templates",
              type=click.Path(exists=True),
              help="Directory containing Jinja2 templates")
def cli(ifc_file, rules, output, templates):
    """Audit an IFC file against BEP/EIR rules. Outputs HTML report."""
    click.echo(f"▸ Loading {ifc_file}...")
    audit = run_audit(ifc_file, rules)

    s = audit["summary"]
    click.echo(f"▸ {s['passed_rules']}/{s['total_rules']} rules passed "
               f"({s['pass_rate'] * 100:.0f}%)")
    click.echo(f"  Critical failures: {s['failed_critical']}")
    click.echo(f"  Major failures:    {s['failed_major']}")
    click.echo(f"  Minor failures:    {s['failed_minor']}")

    click.echo(f"▸ Rendering {output}...")
    render_report(audit, templates, output)
    click.echo(f"✓ Report written: {output}")

    sys.exit(0 if s["failed_critical"] == 0 else 1)


if __name__ == "__main__":
    cli()
