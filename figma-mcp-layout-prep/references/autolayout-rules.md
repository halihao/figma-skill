# Auto Layout Rules

Add Auto Layout only when the geometry strongly suggests a linear structure.

## Safe Candidates

Treat these patterns as safe Auto Layout candidates:

- vertically stacked form fields
- vertically stacked card content
- vertically stacked modal sections
- horizontally aligned action buttons
- horizontally aligned tabs or navigation items
- avatar plus text rows
- repeated cards or list rows with consistent spacing

## Unsafe Candidates

Do not auto-apply Auto Layout to:

- hero banners or marketing compositions
- art-directed landing sections with free placement
- grids with multiple rows and columns unless they are already grouped into row wrappers
- overlapping content stacks
- masked, rotated, or clipped decorative compositions
- nodes whose children rely on absolute placement for visual correctness

Mark these as manual review instead.

## Inference Defaults

Infer layout settings conservatively:

- `layoutMode`: `VERTICAL` for top-to-bottom stacks, `HORIZONTAL` for left-to-right rows
- `itemSpacing`: median positive gap along the main axis
- `padding`: distance from child union bounds to parent bounds
- `counterAxisAlignItems`: `MIN`, `CENTER`, or `MAX` based on cross-axis distribution
- `primaryAxisSizingMode`: usually `AUTO`
- `counterAxisSizingMode`: usually `AUTO` unless the container is clearly stretched by its parent

Infer child sizing conservatively:

- use `layoutAlign = "STRETCH"` and `layoutGrow = 1` when a child nearly spans the full inner cross-axis
- keep fixed sizing when the child has a clearly bounded visual role
- keep `layoutPositioning = "ABSOLUTE"` for overlays such as close buttons, badges, floating icons, and corner chips

## Group Conversion Guidance

Treat a `GROUP` as convertible only when:

- it has two or more children
- the children form a clear vertical or horizontal stack
- siblings do not overlap in a way that would break on reflow
- there is no strong sign that free placement is intentional

If the group looks convertible but the visual risk is non-trivial, report it as `group_conversion_candidate` instead of applying it directly.

## Verification Checklist

After applying Auto Layout:

1. Re-open the screenshot and check visual parity.
2. Confirm overlays still sit in the right place.
3. Confirm spacing did not collapse on nested stacks.
4. Confirm the target subtree is the only region that changed.
5. Re-run metadata inspection if the page is meant for MCP-based code generation next.
