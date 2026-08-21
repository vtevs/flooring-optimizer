# Supplier A/B Strict Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Model supplier A/B boards as physical boards with fixed tongue/groove edges, preserve source-board coordinates through every cut, and prove that every placed and reused piece has a realizable A/B type and rotation.

**Architecture:** Add one supplier-stock module as the authority for A/B edges and rotations. Extend cutting pieces with absolute coordinates in their root source board, then solve placement domains using source type, source cuts, board geometry, and room adjacencies. The optimizer records the solved assignment; verification checks that assignment, and the HTML source diagram renders the same source coordinates instead of reconstructing a fictional sequence.

**Tech Stack:** Python 3.11+, dataclasses, Shapely, pytest, embedded SVG/JavaScript HTML renderer.

---

### Task 1: Supplier Board Edge Model

**Files:**
- Create: `floorplan/stock.py`
- Modify: `floorplan/models.py`
- Test: `tests/test_stock.py`

- [ ] **Step 1: Write failing rotation tests**

```python
def test_supplier_a_rotations_preserve_geometry_and_edges():
    assert supplier_edges("A", 0) == BoardEdges(T, G, G, T)
    assert supplier_edges("A", 90) == BoardEdges(G, T, T, G)
    assert orientation_for_rotation(0) == "vertical"
    assert orientation_for_rotation(90) == "horizontal"

def test_equal_edge_pattern_does_not_make_board_geometry_equal():
    assert supplier_edges("A", 270) == supplier_edges("B", 0)
    assert orientation_for_rotation(270) != orientation_for_rotation(0)
```

- [ ] **Step 2: Verify the tests fail because the stock API is absent**

Run: `venv/bin/pytest tests/test_stock.py -q`

- [ ] **Step 3: Implement the physical definitions and all four rotations**

```python
SUPPLIER_VERTICAL_EDGES = {
    "A": BoardEdges(top=T, right=G, bottom=G, left=T),
    "B": BoardEdges(top=T, right=T, bottom=G, left=G),
}

def supplier_edges(stock_class: str, rotation: int) -> BoardEdges:
    return rotate_edges(SUPPLIER_VERTICAL_EDGES[stock_class], rotation)

def orientation_for_rotation(rotation: int) -> str:
    return "vertical" if rotation % 180 == 0 else "horizontal"
```

- [ ] **Step 4: Run the focused tests**

Run: `venv/bin/pytest tests/test_stock.py -q`
Expected: all stock-model tests pass.

### Task 2: Root Source-Board Cutting Coordinates

**Files:**
- Modify: `floorplan/models.py`
- Modify: `floorplan/layout/board_pool.py`
- Modify: `floorplan/layout/l_triple.py`
- Test: `tests/test_material.py`

- [ ] **Step 1: Write failing source-coordinate tests**

```python
def test_length_reuse_uses_opposite_original_end_once():
    pool = BoardPool(100, kerf=2, board_width=20)
    first = pool.cut_new(30, "1")
    second = pool.take(25, "2")
    assert piece(first).source_y == 0
    assert piece(second).source_y == 75
    assert pool.take(10, "3") is None

def test_combined_cut_rectangles_do_not_overlap():
    pool = BoardPool(100, kerf=2, board_width=20)
    pool.cut_new_combined(40, 8, "1")
    assert source_rect("1") == (0, 0, 8, 40)
```

- [ ] **Step 2: Verify the tests fail on missing coordinates and repeated middle reuse**

Run: `venv/bin/pytest tests/test_material.py -q`

- [ ] **Step 3: Store absolute root-board rectangles**

Add `source_x`, `source_y`, `source_width`, `source_length`, and `root_source_id` to `CuttingPiece`. Add the same absolute bounds to `PoolEntry`. New pieces are anchored at a source-board edge; a second length piece is taken from the opposite original short edge, and the remaining middle strip is not reusable because both short edges are cut.

- [ ] **Step 4: Propagate coordinates into L-triple cutting groups**

```python
CuttingPiece(
    label=p["label"],
    length=p["length"],
    width=p.get("width", 0.0),
    source_x=p.get("source_x", 0.0),
    source_y=p.get("source_y", 0.0),
    source_width=p.get("source_width", board_width),
    source_length=p.get("source_length", p["length"]),
)
```

- [ ] **Step 5: Run pool and layout tests**

Run: `venv/bin/pytest tests/test_material.py tests/test_layout.py -q`

### Task 3: Strict Supplier Assignment Solver

**Files:**
- Create: `floorplan/stock_assignment.py`
- Modify: `floorplan/models.py`
- Modify: `floorplan/layout/l_triple.py`
- Test: `tests/test_stock_assignment.py`

- [ ] **Step 1: Write failing domain and same-source tests**

```python
def test_vertical_piece_only_accepts_zero_or_180_degree_states():
    assert {s.rotation for s in placement_states(vertical_board)} == {0, 180}

def test_same_source_pieces_share_stock_class_but_can_rotate_independently():
    result = solve_supplier_assignment(two_pieces_from_one_source)
    assert result["1"].stock_class == result["2"].stock_class

def test_source_cut_edge_must_land_on_room_cut_side():
    assert solve_supplier_assignment(impossible_cut_orientation).errors
```

- [ ] **Step 2: Verify the solver tests fail because no strict solver exists**

Run: `venv/bin/pytest tests/test_stock_assignment.py -q`

- [ ] **Step 3: Build candidate states from one physical lifecycle**

For every placement, create only states where:

```text
source rectangle dimensions + rotation == placed rectangle dimensions
rotated source CUT sides == geometric room-boundary CUT sides
rotation parity == vertical/horizontal placement orientation
all pieces under one root source use one stock class
```

- [ ] **Step 4: Solve all neighboring T/G constraints**

Use AC-3 plus MRV backtracking. A neighboring pair is allowed only when both touching edges are non-cut and one is `TONGUE` while the other is `GROOVE`. Prefer the stock class with fewer assigned root boards so equal supplier quantities differ by at most one when constraints permit.

- [ ] **Step 5: Record the solved state**

Add `stock_class`, `source_rotation`, and `display_edges` to `PlacedBoard`; copy the root stock class into every related `CuttingGroup`. Add source-count and purchased-count fields to `LayoutStatistics`.

- [ ] **Step 6: Run focused solver tests**

Run: `venv/bin/pytest tests/test_stock.py tests/test_stock_assignment.py tests/test_verify_edges.py -q`

### Task 4: Optimization and Verification Integration

**Files:**
- Modify: `floorplan/layout/l_triple.py`
- Modify: `floorplan/multi_optimize.py`
- Modify: `floorplan/verify.py`
- Modify: `floorplan/cli.py`
- Test: `tests/test_layout.py`
- Test: `tests/test_verify_edges.py`

- [ ] **Step 1: Write failing integration tests**

```python
def test_supplier_policy_records_strict_assignment_for_every_board():
    result = LTripleEngine().layout(room, supplier_board)
    assert all(b.stock_class in {"A", "B"} for b in result.boards)
    assert all(b.source_rotation in {0, 90, 180, 270} for b in result.boards)

def test_verifier_rejects_tampered_same_source_stock_class():
    result.boards[1].stock_class = opposite(result.boards[0].stock_class)
    assert any("同源板型不一致" in e for e in verify_layout(result, config))
```

- [ ] **Step 2: Verify the integration tests fail on the old independent solver**

Run: `venv/bin/pytest tests/test_layout.py tests/test_verify_edges.py -q`

- [ ] **Step 3: Assign during each L-triple candidate and reject infeasible candidates**

The L-triple engine runs strict assignment after constructing cutting groups. `multi_optimize.py` ignores candidates marked infeasible and compares feasible candidates by required equal-mix purchase count first, consumed source-board count second, and waste area third.

- [ ] **Step 4: Make verification check recorded physical facts**

Under `supplier-ab-vertical`, verification must not invent rotations. It recomputes each piece's source edges from stock type and absolute source rectangle, rotates them by `source_rotation`, compares them with room cut sides, validates same-root stock class, and checks every internal adjacency.

- [ ] **Step 5: Report A/B consumption and equal-mix purchase count**

Add CLI lines for `A 型源板`, `B 型源板`, `实际消耗`, and `按 1:1 配板采购`.

- [ ] **Step 6: Run integration tests**

Run: `venv/bin/pytest tests/test_layout.py tests/test_verify_edges.py tests/test_cli.py -q`

### Task 5: Exact HTML Source Diagram

**Files:**
- Modify: `floorplan/svg/html_renderer.py`
- Test: `tests/test_html_renderer.py`

- [ ] **Step 1: Write failing HTML tests**

```python
def test_source_layout_uses_absolute_piece_rectangles():
    layout = reconstruct(result)
    assert layout["source-1"]["pieces"][1]["y"] == 75

def test_modal_contains_source_validation_and_physical_rotation():
    html = build_html(...)
    assert "源板切割校验：通过" in html
    assert "铺装旋转" in html
```

- [ ] **Step 2: Verify the renderer tests fail on sequential offsets**

Run: `venv/bin/pytest tests/test_html_renderer.py -q`

- [ ] **Step 3: Render the canonical source board and exact rectangles**

Draw the source board vertically (`width × length`) so its top/right/bottom/left correspond directly to the user's definition. Render every piece at its absolute `source_x/source_y`, draw kerf/waste as the uncovered region, mark the clicked piece, and display the source stock type and validation result.

- [ ] **Step 4: Use recorded edges in the modal**

The room board and source diagram must both use `PlacedBoard.display_edges`; remove the renderer call that independently asks the verifier to invent an assignment.

- [ ] **Step 5: Run renderer tests**

Run: `venv/bin/pytest tests/test_html_renderer.py -q`

### Task 6: Documentation and End-to-End Verification

**Files:**
- Modify: `docs/flooring_constraints.md`
- Modify: `README.md`
- Modify: `projects/home-wood-l-triple/config-full-board-corner.yaml`

- [ ] **Step 1: Update the authoritative physical definitions**

Document A and B in their vertical zero-degree state, all four permitted rotations, source-coordinate cutting inheritance, same-source stock-class invariants, and the equal-mix purchase objective. Remove conflicting single-board top/bottom definitions from the active supplier-policy section.

- [ ] **Step 2: Run the full suite**

Run: `venv/bin/pytest tests/ -q`
Expected: all tests pass.

- [ ] **Step 3: Run the target configuration into a temporary directory**

Run: `venv/bin/python -m floorplan projects/home-wood-l-triple/config-full-board-corner.yaml -o /tmp/floorplan-ab-strict`
Expected: strict source-cut and adjacency verification passes, with A/B source counts and equal-mix purchase count printed.

- [ ] **Step 4: Inspect generated HTML data and SVG structure**

Check that every board has A/B type, source rotation, four physical edges, and an in-bounds source rectangle; check that no rectangles from one source overlap and that every source diagram reports validation passed.

- [ ] **Step 5: Review the final diff without changing unrelated files**

Run: `git diff --check` and `git status --short`.
