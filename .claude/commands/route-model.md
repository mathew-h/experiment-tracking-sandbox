Classify the current task and select the appropriate Claude model. Output valid JSON only, then run `/model <alias>`.

## Model IDs
| Alias  | Full model ID             |
|--------|---------------------------|
| haiku  | claude-haiku-4-5-20251001 |
| sonnet | claude-sonnet-4-6         |
| opus   | claude-opus-4-6           |

## Output (exactly this shape, one line)
```json
{"model": "haiku"|"sonnet"|"opus", "reason": "one sentence", "confidence": "high"|"medium"|"low"}
```
Then run: `/model <chosen alias>` and tell the user in one sentence.

## Routing policy
**Default: haiku.** Optimize for lowest cost that still succeeds on first pass.

| Model  | Use when |
|--------|----------|
| **haiku**  | Single file/document questions, summarization, extraction, narrow Q&A, metadata lookup, no code changes. |
| **sonnet** | Codebase search, multi-file reasoning, any edits/implementation/debugging/refactoring/tests, or task that involves changing code. |
| **opus**   | Large-scale architecture, cross-system redesign, migration strategy, deep synthesis across many files, high-stakes tasks where a shallow answer would fail. |

## Rules
1. Any task involving code changes → **at least sonnet**.
2. Opus is **exceptional** — not for “hard” tasks that sonnet can handle.
3. If uncertain between two models → choose the **cheaper** one.
4. Base the choice on the **work required**, not on phrasing like “best” or “thorough”.

## Quick escalation
- **Haiku → Sonnet:** request involves code, multiple files, edits, or non-trivial reasoning.
- **Sonnet → Opus:** many files/systems, architecture/migration/redesign, high ambiguity or high cost of a wrong first pass.

---

**Task to classify:** $ARGUMENTS
