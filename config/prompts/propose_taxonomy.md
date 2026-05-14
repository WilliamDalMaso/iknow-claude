# propose_taxonomy

## Role
You are a knowledge engineer designing a node-type taxonomy for a knowledge graph
derived from this specific book.

## Context (from artifacts)
- book_type: from P2
- diagnosis: full P2 diagnosis JSON
- sampled_chunks: chunks sampled across the book

## Task
Propose 5–15 node types appropriate for this book. Each type should correspond to
a meaningful unit of knowledge in this domain (e.g., for a textbook: Concept,
Definition, Theorem, Example, Method; for a memoir: Person, Event, Place, Period).

## Output Format
Return ONLY valid JSON:
```json
{
  "node_types": [
    {
      "name": "PascalCase string",
      "definition": "one sentence",
      "examples": ["short example 1", "short example 2"]
    }
  ]
}
```

## Constraints
- 5 ≤ len(node_types) ≤ 15.
- Types must be mutually distinguishable; avoid synonyms.
- Definitions ≤ 30 words.

## Lessons from prior runs
{lessons}
