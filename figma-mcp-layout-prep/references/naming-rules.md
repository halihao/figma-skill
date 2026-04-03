# Naming Rules

Apply semantic, machine-friendly names that help developers and Figma MCP understand structure at a glance.

## Core System

Use slash-separated names with a stable prefix:

- `page/<domain>`
- `screen/<page-name>`
- `section/<purpose>`
- `layout/<purpose>`
- `group/<purpose>`
- `card/<purpose>`
- `list/<purpose>`
- `form/<purpose>`
- `nav/<purpose>`
- `modal/<purpose>`
- `text/title`
- `text/subtitle`
- `text/body`
- `text/label`
- `text/value`
- `text/helper`
- `image/<purpose>`
- `icon/<purpose>`
- `bg/<purpose>`
- `divider/horizontal`
- `divider/vertical`
- `overlay/<purpose>`

Use kebab-case for the suffix. Avoid spaces, punctuation, and raw Chinese copy in the final node name when the goal is development handoff consistency.

## Keep or Change

Keep the existing name when:

- the node is a component instance with a useful component name
- the current name already encodes intent cleanly
- changing the name would erase a team-specific convention that still helps developers

Rename the node when:

- it uses a default Figma name such as `Frame 12`, `Group 3`, `Rectangle 8`, `Text 5`
- it contains only visual type information and no intent
- it duplicates sibling names in a way that makes handoff ambiguous

## Suggested Mapping Heuristics

Apply these heuristics in order:

1. Treat top-level page children as `screen/*` unless the existing name already looks like `section/*`.
2. Treat containers with stable horizontal or vertical stacking as `layout/*`.
3. Treat repeated item wrappers as `list/*` or `card/*`.
4. Treat large background shapes as `bg/*`.
5. Treat thin separators as `divider/horizontal` or `divider/vertical`.
6. Treat small decorative vectors or shapes as `icon/*`.
7. Treat text using visual hierarchy:
   - tallest or most prominent text in a block -> `text/title`
   - supporting headline -> `text/subtitle`
   - normal paragraph or row text -> `text/body`
   - form caption or field title -> `text/label`
   - value or metric readout -> `text/value`
   - fine print, hint, or validation copy -> `text/helper`

## Repeated Structures

When siblings have similar type and size:

- name the parent `list/<purpose>` if it behaves like a repeated vertical or horizontal collection
- name each repeated child with a stable numbered suffix when intent is still unclear, such as `card/item-1`, `card/item-2`

Prefer consistency over cleverness. Developers benefit more from stable patterns than from overly specific guesses.

## Things to Avoid

- `Frame 1`, `Group 2`, `Rectangle 3`, `Text 4`
- names based only on copy content when that content may change later
- names that mix presentation and semantics such as `blue-button-big`
- deeply nested names with more than two slash segments unless the team already depends on them
