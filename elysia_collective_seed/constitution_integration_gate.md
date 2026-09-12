# AI Constitution Integration Gate

## Status

An AI Constitution / Elysia Covenant already exists in the historical project material. **Do not create a replacement constitution.**

The existing constitution is a primary governance source and must be imported from the historical source material before any Collective runtime treats a reconstructed summary as authoritative.

## Integration rule

Until the original text is recovered and verified:

- Collective prompts may follow existing Guardian safety boundaries and the bounded seed rules.
- No new file may claim to supersede, revise, or replace the historical AI Constitution.
- Any remembered or reconstructed constitutional principle must be labeled `RECOVERED_SUMMARY`, not `AUTHORITATIVE_TEXT`.
- The original constitution, once located, should enter Genesis Memory unchanged with source/date/version metadata.
- Machine-readable governance rules should be derived from the verified constitution through a separate traceable mapping file.
- Every machine rule should point back to the constitutional clause or source passage that authorized it.
- Conflicts between new Collective design and the verified constitution must be surfaced for human review rather than silently reconciled.

## Intended architecture

```text
Verified AI Constitution / Covenant (immutable Genesis source)
                    |
                    v
        Constitutional Clause Index
                    |
                    v
        Machine Governance Mapping
                    |
          +---------+---------+
          |                   |
          v                   v
   Agent permissions      Human approval gates
          |                   |
          +---------+---------+
                    v
             Runtime policies
```

## Source classes

- `AUTHORITATIVE_TEXT`: exact imported historical constitution/covenant text.
- `RECOVERED_SUMMARY`: remembered or conversation-derived summary pending source verification.
- `IMPLEMENTATION_MAPPING`: machine policy derived from a verified clause.
- `PROPOSED_AMENDMENT`: later proposal that does not alter the historical source.

## Amendment discipline

If the constitution is ever revised, preserve the prior version. Amendments should be additive/versioned and record who proposed them, why, which clauses change, and the approval event. Historical versions remain readable.

## Current gate

Runtime governance integration remains blocked on recovery of the original constitutional source text from the user's Elysia ChatGPT Project, local Guardian archive, ChatGPT export, or other verified historical source.
