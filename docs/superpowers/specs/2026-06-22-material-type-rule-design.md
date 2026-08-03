# Material Type Rule Design

## Goal

Add a top-level material configuration that chooses whether the layout is treated as tongue-and-groove wood flooring or as tile. The balcony project uses tile, which has no tongue/groove structure and can reuse cut pieces by size.

## Configuration

```yaml
material:
  type: tile   # wood | tile
```

Default is `wood` for backward compatibility.

## Wood Behavior

Wood keeps the current rules:

- internal neighboring edges must prove T/G compatibility;
- cut edges are not allowed on internal neighboring edges;
- edge-aware reuse may reject pieces whose retained/cut sides cannot satisfy a placement requirement.

## Tile Behavior

Tile changes only material-specific constraints:

- skip the T/G edge proof entirely;
- allow cut edges between internal neighbors because tile has no tongue/groove;
- reuse cut pieces by dimensions only, without edge-type matching.

Tile still uses the same geometry, pattern, board/tile size, kerf, expansion gap, board gap, cutting area checks, and coverage checks.

## Scope

The material is selected for the whole config, not per room. Mixed-material rooms are out of scope for this change.

## Failure Behavior

Unknown material types fail during config parsing with a clear error. Verification continues to report cutting and coverage errors for both materials.
