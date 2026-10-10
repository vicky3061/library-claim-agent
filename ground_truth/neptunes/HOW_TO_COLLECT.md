# Collecting ground truth

Do this BEFORE tuning anything (brief requirement). Fill these by hand, not from the system.
Time needed: about 60–90 minutes for a room with 60–100 books.

## Naming convention (use the same one everywhere)
- **shelf_unit**: A, B, C… left to right as you enter the room. Stick ArUco marker ID 0 on unit A, ID 1 on unit B, etc.
- **shelf_row**: 1 = top row, counting down.
- **position**: 1 = leftmost book on that row, counting right. For a flat stack, count top to bottom and set `orientation=flat`.

## books.csv — every book
One row per physical book. `legible=yes` only if YOU can read the title from the spine at normal distance without pulling the book out. Title/author exactly as on the spine. Leave blank if you can't read it.
This gives: true book count, and the "human-legible spines" denominator for the 70% bar.

## spine_measurements.csv — 20 books
Pick 20 spread across all units and rows (not just the easy ones): some thin, some thick, some tall, a couple flat.
Height = top to bottom of spine. Thickness = spine width. Centimetres, one decimal.

## prices.csv — 15 books
For 15 identified books, look up by hand on the same type of source the system uses (e.g. the publisher/retailer new price, and a used listing). Record URL and date.
Mix cheap paperbacks, hardcovers, and one or two older/unusual books.

## items.csv — every non-book item
Shelving units count as items. Note brand/model only if visible. For art, write whether it is a print or an original.

## room.csv — tape measurements
Measure floor-level wall to wall. Ceiling height at one corner.
Our wall-area definition (state in README): gross wall area = perimeter × ceiling height, doors and windows NOT subtracted.
If the room is not a rectangle, describe the shape and measure each wall segment in notes.

## Second space (unseen test)
Collect a smaller set (one shelf unit: count, 10 titles, room tape) in a second space we never tune on.
