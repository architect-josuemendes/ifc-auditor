"""
Generate a synthetic IFC4 file with realistic structure AND intentional issues
so the ifc-auditor has things to find.

This produces examples/sample.ifc, a small office building with:
  - 1 site, 1 building, 3 storeys
  - ~30 walls, ~12 doors, ~24 windows, ~3 slabs
  - Some walls intentionally missing FireRating (property completeness check)
  - Some elements intentionally without material assignment
  - Project naming intentionally non-compliant with ISO 19650 Annex C
  - Some elements not assigned to a spatial structure (orphan elements)

Run:
    python generate_sample.py
"""
import ifcopenshell
import ifcopenshell.api
import random
import uuid

random.seed(42)


def create_guid() -> str:
    """Generate IFC-compliant GUID."""
    return ifcopenshell.guid.new()


def main():
    # Create blank IFC4 model
    model = ifcopenshell.api.run("project.create_file", version="IFC4")

    # === PROJECT ===
    # Intentionally non-ISO19650-compliant name (auditor should flag this)
    project = ifcopenshell.api.run(
        "root.create_entity", model,
        ifc_class="IfcProject",
        name="Sample Office Building"  # NOT compliant with PR-OR-VL-LO format
    )

    # Units
    ifcopenshell.api.run("unit.assign_unit", model)

    # Context
    context = ifcopenshell.api.run(
        "context.add_context", model, context_type="Model"
    )
    body_context = ifcopenshell.api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body",
        target_view="MODEL_VIEW", parent=context
    )

    # === SPATIAL STRUCTURE ===
    site = ifcopenshell.api.run(
        "root.create_entity", model,
        ifc_class="IfcSite", name="Test Site"
    )
    ifcopenshell.api.run(
        "aggregate.assign_object", model,
        relating_object=project, products=[site]
    )

    building = ifcopenshell.api.run(
        "root.create_entity", model,
        ifc_class="IfcBuilding", name="Main Building"
    )
    ifcopenshell.api.run(
        "aggregate.assign_object", model,
        relating_object=site, products=[building]
    )

    # 3 storeys
    storeys = []
    for level in range(3):
        s = ifcopenshell.api.run(
            "root.create_entity", model,
            ifc_class="IfcBuildingStorey",
            name=f"Level {level:02d}"
        )
        storeys.append(s)
    ifcopenshell.api.run(
        "aggregate.assign_object", model,
        relating_object=building, products=storeys
    )

    # === MATERIALS ===
    concrete = ifcopenshell.api.run(
        "material.add_material", model,
        name="Concrete C30/37", category="concrete"
    )
    gypsum = ifcopenshell.api.run(
        "material.add_material", model,
        name="Gypsum board", category="gypsum"
    )
    steel = ifcopenshell.api.run(
        "material.add_material", model,
        name="Steel S355", category="steel"
    )
    timber = ifcopenshell.api.run(
        "material.add_material", model,
        name="Glulam GL24h", category="timber"
    )
    materials = [concrete, gypsum, steel, timber]

    # === WALLS ===
    walls = []
    for level_idx, storey in enumerate(storeys):
        for w_idx in range(10):
            wall = ifcopenshell.api.run(
                "root.create_entity", model,
                ifc_class="IfcWall",
                name=f"Wall-{level_idx:02d}-{w_idx:03d}"
            )
            ifcopenshell.api.run(
                "spatial.assign_container", model,
                relating_structure=storey, products=[wall]
            )
            walls.append(wall)

            # INTENTIONAL ISSUE: ~30% of walls missing FireRating property
            if random.random() > 0.30:
                pset = ifcopenshell.api.run(
                    "pset.add_pset", model,
                    product=wall, name="Pset_WallCommon"
                )
                ifcopenshell.api.run(
                    "pset.edit_pset", model,
                    pset=pset,
                    properties={
                        "FireRating": random.choice(["F30", "F60", "F90"]),
                        "IsExternal": random.choice([True, False]),
                        "LoadBearing": random.choice([True, False]),
                    }
                )

            # INTENTIONAL ISSUE: ~15% of walls without material
            if random.random() > 0.15:
                ifcopenshell.api.run(
                    "material.assign_material", model,
                    products=[wall],
                    type="IfcMaterial",
                    material=random.choice(materials)
                )

    # === DOORS ===
    for level_idx, storey in enumerate(storeys):
        for d_idx in range(4):
            door = ifcopenshell.api.run(
                "root.create_entity", model,
                ifc_class="IfcDoor",
                name=f"Door-{level_idx:02d}-{d_idx:03d}"
            )
            ifcopenshell.api.run(
                "spatial.assign_container", model,
                relating_structure=storey, products=[door]
            )

            # INTENTIONAL ISSUE: ~50% of doors missing IsExternal
            if random.random() > 0.50:
                pset = ifcopenshell.api.run(
                    "pset.add_pset", model,
                    product=door, name="Pset_DoorCommon"
                )
                ifcopenshell.api.run(
                    "pset.edit_pset", model,
                    pset=pset,
                    properties={
                        "IsExternal": random.choice([True, False]),
                        "FireRating": random.choice(["F30", "F60", ""]),
                    }
                )

    # === WINDOWS ===
    for level_idx, storey in enumerate(storeys):
        for w_idx in range(8):
            window = ifcopenshell.api.run(
                "root.create_entity", model,
                ifc_class="IfcWindow",
                name=f"Window-{level_idx:02d}-{w_idx:03d}"
            )
            ifcopenshell.api.run(
                "spatial.assign_container", model,
                relating_structure=storey, products=[window]
            )

    # === SLABS ===
    for level_idx, storey in enumerate(storeys):
        slab = ifcopenshell.api.run(
            "root.create_entity", model,
            ifc_class="IfcSlab",
            name=f"Slab-{level_idx:02d}-001"
        )
        ifcopenshell.api.run(
            "spatial.assign_container", model,
            relating_structure=storey, products=[slab]
        )
        ifcopenshell.api.run(
            "material.assign_material", model,
            products=[slab], type="IfcMaterial", material=concrete
        )

    # === INTENTIONAL ISSUE: 2 orphan elements (not assigned to any storey) ===
    for i in range(2):
        orphan = ifcopenshell.api.run(
            "root.create_entity", model,
            ifc_class="IfcFurnishingElement",
            name=f"Orphan-Element-{i:03d}"
        )
        # Do NOT assign to storey

    # Save
    output_path = "examples/sample.ifc"
    model.write(output_path)
    print(f"✓ Synthetic IFC generated: {output_path}")
    print(f"  Project name: '{project.Name}' (intentionally NOT ISO 19650 compliant)")
    print(f"  Walls: 30  (intentional gaps in FireRating + material)")
    print(f"  Doors: 12  (intentional gaps in IsExternal)")
    print(f"  Windows: 24")
    print(f"  Slabs: 3")
    print(f"  Orphans: 2 (intentionally not assigned to a storey)")


if __name__ == "__main__":
    main()
