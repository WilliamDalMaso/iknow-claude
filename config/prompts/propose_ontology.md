# propose_ontology

## Role
You design the edge-type ontology that connects node types in the knowledge graph.

## Context (from artifacts)
- node_types: output of propose_taxonomy
- book_type: from P2
- sampled_chunks: chunks sampled across the book

## Task
Propose 5–12 edge types appropriate for the given node types and book domain.
Each edge type must specify allowed source and target node types.

## Output Format
Return ONLY valid JSON:
```json
{
  "edge_types": [
    {
      "name": "snake_case_string",
      "definition": "one sentence",
      "allowed_source_types": ["NodeTypeName", ...],
      "allowed_target_types": ["NodeTypeName", ...]
    }
  ]
}
```

## Constraints
- 5 ≤ len(edge_types) ≤ 12.
- Every allowed_source_types / allowed_target_types entry must appear in node_types.
- No redundant inverses (don't pair "is_part_of" with "has_part" — pick one).

## Lessons from prior runs
{lessons}
