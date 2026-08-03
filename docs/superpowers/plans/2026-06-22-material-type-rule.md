# Material Type Rule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add config-level `material.type` so wood keeps T/G rules and tile skips T/G while reusing pieces by size.

**Architecture:** Parse material into `Config.material`, pass material type into layout pools, and make verification branch on material. Keep geometry, coverage, and cutting checks shared.

**Tech Stack:** Python 3.11, PyYAML, Shapely, pytest.

---

### Task 1: Config Model And Parsing

**Files:**
- Modify: `floorplan/models.py`
- Modify: `floorplan/config.py`
- Test: `tests/test_config.py`

- [ ] Add `MaterialType` enum with `wood` and `tile`.
- [ ] Add `MaterialConfig(type=MaterialType.WOOD)` to top-level `Config`.
- [ ] Parse optional top-level `material.type`, defaulting to wood.
- [ ] Reject unknown material types.

### Task 2: Verification Branch

**Files:**
- Modify: `floorplan/verify.py`
- Test: `tests/test_material.py`

- [ ] Keep `_verify_cutting_ops` and `_verify_coverage` for every material.
- [ ] Skip `_verify_edges` and `verify_edge_details` for tile configs.
- [ ] Prove wood still rejects internal cut edges.
- [ ] Prove tile accepts the same layout while still running other verification paths.

### Task 3: Tile Size-Only Reuse

**Files:**
- Modify: `floorplan/layout/board_pool.py`
- Modify: layout engines that create `BoardPool`
- Test: `tests/test_material.py`

- [ ] Add `material_type` to `BoardPool`.
- [ ] In tile mode, ignore `required_edges` during pool matching.
- [ ] Pass `material_type` from optimizers to layout engines and pools.
- [ ] Prove a mismatched-edge leftover can be reused in tile mode but not wood mode.

### Task 4: Balcony Config And Verification

**Files:**
- Modify: `projects/balcony/config.yaml`
- Generated: `projects/balcony/output/floor_plan.svg`
- Generated: `projects/balcony/output/cutting_plan.txt`

- [ ] Add `material.type: tile` to balcony config.
- [ ] Generate balcony output.
- [ ] Run full test suite.
