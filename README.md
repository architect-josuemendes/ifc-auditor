# ifc-auditor

> **Validate IFC files against configurable BEP / EIR rules before they reach the Common Data Environment.**
> Pure Python · YAML-configurable · HTML reports · ISO 19650-aligned.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org)
[![IFC](https://img.shields.io/badge/IFC-IFC4%20·%20IFC4X3-A4471F)](https://www.buildingsmart.org)
[![Stack](https://img.shields.io/badge/Stack-ifcopenshell%20·%20click%20·%20jinja2-15803D)](#tech-stack)

---

## TL;DR

The problem: BIM Managers receive IFC deliverables from sub-consultants. Before uploading them to the CDE, they need to verify that the model complies with the project's **BEP** (BIM Execution Plan) and **EIR** (Exchange Information Requirements). Manual inspection in a viewer is slow, error-prone, and inconsistent.

The solution: a small, configurable command-line tool that runs in seconds and produces a clean HTML audit report.

```bash
python audit.py building.ifc --rules my_bep.yaml --output report.html
```

→ Result: a navigable HTML report with pass/fail per rule, drill-down to failing GUIDs, and an overall pass-rate score.

---

## Live sample report

See **[`examples/sample_report.html`](examples/sample_report.html)** for the audit output of the included synthetic IFC. Headline: 4/10 rules passed (40%), 0 critical failures, 5 major failures, 1 minor failure — a typical "deliverable with issues to fix" profile.

---

## Why this exists

Most clash-detection workflows operate **after** the IFC reaches the CDE. By then, finding that a discipline forgot to populate `Pset_WallCommon.FireRating` on 144 walls means another federation cycle, another coordination meeting, another week lost.

This tool moves validation **left** — before the IFC is even accepted. Run it on every consultant delivery, return a clean report with what's missing, send it back with concrete action items.

It's intentionally small. The whole pipeline is two Python files (`audit.py` + `generate_sample.py`), one YAML config, and one Jinja2 template. Read it in 15 minutes, adapt it in an hour.

---

## What it checks

The included `rules.yaml` ships with 10 rules across 5 categories. Each rule is configurable per project.

| Category | Rule | What it validates |
|---|---|---|
| **Project metadata** | `naming_iso19650` | `IfcProject.Name` matches ISO 19650 Annex C pattern |
| | `schema_version` | IFC schema is IFC4 or IFC4X3 |
| **Spatial structure** | `storey_count` | Project has at least one `IfcBuildingStorey` |
| | `spatial_orphans` | All physical elements assigned to a spatial structure |
| **Properties** | `wall_firerating` | All walls have `Pset_WallCommon.FireRating` |
| | `wall_loadbearing` | All walls have `Pset_WallCommon.LoadBearing` |
| | `door_isexternal` | All doors have `Pset_DoorCommon.IsExternal` |
| **Materials** | `wall_material` | All walls have material assignment |
| | `slab_material` | All slabs have material assignment |
| **Integrity** | `unique_guids` | All `GlobalId`s are unique across the model |

Each rule has a `severity` (critical | major | minor):
- **critical** — blocks model acceptance
- **major** — requires remediation before construction
- **minor** — documented as RFI-track items

---

## Run it in 60 seconds

```bash
# Clone
git clone https://github.com/architect-josuemendes/ifc-auditor.git
cd ifc-auditor

# Install dependencies
pip install -r requirements.txt

# Generate the synthetic test IFC (small office, intentional issues built in)
python generate_sample.py

# Run the audit
python audit.py examples/sample.ifc --rules rules.yaml --output report.html

# Open the report in your browser
open report.html        # macOS
# xdg-open report.html  # Linux
# start report.html     # Windows
```

You'll see a CLI summary like:

```
▸ Loading examples/sample.ifc...
▸ 4/10 rules passed (40%)
  Critical failures: 0
  Major failures:    5
  Minor failures:    1
▸ Rendering report.html...
✓ Report written: report.html
```

Exit code is `0` if all *critical* rules pass, `1` otherwise. Perfect for CI/CD integration.

---

## Repository structure

```
.
├── README.md                       # this file
├── LICENSE                         # MIT
├── requirements.txt                # ifcopenshell, click, jinja2, pyyaml, pydantic
├── audit.py                        # main CLI tool (~370 lines)
├── generate_sample.py              # synthetic IFC generator (~180 lines)
├── rules.yaml                      # example rules configuration
├── templates/
│   └── report.html.j2              # Jinja2 HTML report template
└── examples/
    ├── sample.ifc                  # synthetic test IFC (16 KB)
    └── sample_report.html          # sample audit report output
```

---

## Adapt to your project

Copy `rules.yaml` and customize per your BEP. Each rule has the same minimal structure:

```yaml
- id: my_rule_id
  name: "Human-readable rule name"
  severity: major
  check:
    type: property_required
    ifc_class: IfcWall
    pset: Pset_WallCommon
    property: ThermalTransmittance
```

Supported `check.type` values:

- `regex` — match a target value against a regex pattern
- `schema` — verify IFC schema version
- `count_min` — verify minimum count of an IFC class
- `property_required` — verify a property is present on all elements of a class
- `material_required` — verify material assignment is present
- `spatial_orphans` — find elements not assigned to a spatial structure
- `unique_guids` — find duplicate GlobalIds

To add a new check type, write a function in `audit.py` (~15 lines) and register it in the `CHECKS` dict.

---

## Tech stack

`Python 3.10+` · `ifcopenshell 0.8+` · `click` (CLI) · `Jinja2` (templating) · `PyYAML` (config) · `pydantic` (schema validation)

---

## CI/CD integration

The CLI exits with status `1` when any critical rule fails, making it drop-in for any CI pipeline:

```yaml
# .github/workflows/ifc-audit.yml
name: IFC Audit
on: [push, pull_request]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - run: python audit.py models/architecture.ifc --rules bep.yaml
```

---

## Author

**Josue Mendes** — Diplom-Architekt · BIM Lead · Munich
Specializing in BIM coordination, AEC data analytics, and federated digital twin systems.

- Portfolio: [josuemendes.vercel.app](https://josuemendes.vercel.app)
- Related: [bim-clash-analytics-caracas](https://github.com/architect-josuemendes/bim-clash-analytics-caracas) — data-driven coordination case study (340 → 20 clashes)
- Research (SILVIA federated Digital Twin): [zenodo.org/records/19616669](https://zenodo.org/records/19616669)
- Email: josuemendesv@gmail.com

Available for AEC-niche freelance work: BIM coordination, openBIM validation, Python automation, AI/LLM integration.

---

## License

MIT — see [`LICENSE`](LICENSE). Use freely, adapt to your projects, attribution welcome.
