# Task

Build a hierarchical topic directory for the supplied entities from one conversation. The directory will support later joint review of their evidence.

# Organization

Start with broad aspects and introduce more specific subtopics where useful. Use at most MAX_TOPIC_DEPTH topic levels; branches may have different depths.

Keep possible duplicate entries and closely connected objects in the same specific branch, including a collection and its members, or an activity and its projects. Stop subdividing when the entities form a coherent review scope. Do not merge or rewrite entities.

Assign every supplied entity exactly once. Preserve its name and ID.

# Output

Return the complete hierarchy as JSON.

Each group has:

- name: A concise topic label.
- description: One sentence describing the scope of its descendants.
- entitie: Exact supplied entity names.
- entity_ids: Corresponding IDs in the same order.
- children: Subgroups with the same structure.

A group contains either subgroups or entities:

- With subgroups, entitie and entity_ids are empty.
- With entities, children is empty.

{ "groups": [ { "name": "...", "description": "...", "entitie": [], "entity_ids": [], "children": [ { "name": "...", "description": "...", "entitie": ["...", "..."], "entity_ids": ["E01", "E07"], "children": [] }, { "name": "...", "description": "...", "entitie": ["...", "..."], "entity_ids": ["E02", "E11"], "children": [] } ] } ] }

# Input

MAX_TOPIC_DEPTH: 3

ENTITIES:

{ENTITIES}
