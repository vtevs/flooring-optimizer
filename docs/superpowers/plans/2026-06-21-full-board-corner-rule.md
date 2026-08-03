# Full Board Corner Rule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable rule requiring every room to have at least one installable-area corner covered by a full uncut board.

**Architecture:** Add one boolean to `InstallationConfig`, parse it from YAML, and filter optimizer candidate layouts through a small helper that checks room-corner coverage. Keep the rule independent from a specific layout engine so single-room and multi-room flows share the same behavior.

**Tech Stack:** Python 3.11, Shapely, PyYAML, pytest.

---

### Task 1: Configuration Model

**Files:**
- Modify: `floorplan/models.py`
- Modify: `floorplan/config.py`
- Test: `tests/test_config.py`

- [ ] Add `require_full_board_at_room_corner: bool = False` to `InstallationConfig`.
- [ ] Parse `installation.require_full_board_at_room_corner` as a boolean in `floorplan/config.py`.
- [ ] Add tests proving the default is `False` and explicit `true` becomes `True`.

### Task 2: Corner Rule Helper

**Files:**
- Create: `floorplan/corner_rule.py`
- Test: `tests/test_corner_rule.py`

- [ ] Implement `has_full_board_at_room_corner(result, room, tolerance=1.0) -> bool`.
- [ ] Treat a candidate corner as satisfied when it lies inside or on a full, uncut board polygon.
- [ ] Test a full board covering bottom-left passes.
- [ ] Test cut-only coverage fails.
- [ ] Test a full board away from corners fails.

### Task 3: Optimizer Filtering

**Files:**
- Modify: `floorplan/optimize.py`
- Modify: `floorplan/multi_optimize.py`
- Test: `tests/test_corner_rule.py`

- [ ] Pass `require_full_board_at_room_corner` from CLI calls into `optimize` and `optimize_multi`.
- [ ] Filter single-room candidates during grid search.
- [ ] Filter multi-room per-room best candidates during coarse and fine search.
- [ ] Raise a room-specific error if a multi-room layout cannot satisfy the rule.

### Task 4: Example Config And Verification

**Files:**
- Modify: `projects/three-l-multi-room/config_ok.yaml`
- Generated: `projects/three-l-multi-room/output_ok/floor_plan.svg`
- Generated: `projects/three-l-multi-room/output_ok/cutting_plan.txt`

- [ ] Enable `require_full_board_at_room_corner: true` in `config_ok.yaml`.
- [ ] Run `python -m floorplan projects/three-l-multi-room/config_ok.yaml -o projects/three-l-multi-room/output_ok`.
- [ ] Run `python -m pytest tests/ -q`.
