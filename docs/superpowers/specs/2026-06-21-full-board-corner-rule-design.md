# Full Board Corner Rule Design

## Goal

Add an optional installation rule: when enabled, each room must have at least one room corner that starts with a full, uncut board. The optimizer should still minimize waste among layouts that satisfy the rule.

## Configuration

The rule is controlled under `installation`:

```yaml
installation:
  pattern: l-triple
  direction: 0
  stagger_ratio: 0.5
  require_full_board_at_room_corner: true
```

Default is `false` for backward compatibility.

## Rule Semantics

The rule applies after the room polygon has been converted to the installable area:

- obstacles are removed;
- expansion gaps are applied;
- board gaps remain part of board placement spacing.

For each room, the optimizer checks the installable area's bounding-box corners:

- bottom-left;
- bottom-right;
- top-left;
- top-right.

The room passes when at least one of those corners is covered by a placed board that is not cut. The corner does not need to be selected by configuration; the optimizer may choose whichever corner gives the lowest waste.

For multi-room layouts, every room must satisfy this rule independently. A candidate layout that fails the rule for any room is rejected.

## Optimization Approach

The rule is implemented as candidate filtering during offset search:

- existing offset search still generates candidate layouts;
- when the rule is enabled, candidates that do not satisfy the corner rule are ignored;
- the best remaining candidate is selected by the existing utilization/board-count logic.

This preserves the optimizer's current objective while adding a施工偏好 constraint.

## Failure Behavior

If no valid layout satisfies the rule, optimization fails with a clear runtime error. Multi-room failures include the room name.

## Testing

Coverage should include:

- YAML parsing default `false`;
- YAML parsing explicit `true`;
- helper-level detection for a full board at an installable room corner;
- rejection when the corner is only covered by cut boards;
- multi-room optimization with the rule enabled using `config-full-board-corner.yaml`.
