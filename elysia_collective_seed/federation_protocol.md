# Elysia Federation Protocol

## Purpose
Allow other people's agents or external agent networks to exchange selected knowledge with Elysia without granting them access to private Guardian state, account data, Genesis Memory, credentials, or internal tools.

## Membrane model
External systems communicate through a gateway. They never connect directly to Collective Memory. Every inbound item enters a quarantine/review stage and every outbound item is an explicitly exportable derivative.

## Inbound flow
1. Receive a federation packet plus sender/network identity metadata.
2. Validate schema, size, provenance fields, and requested operation.
3. Mark all substantive inbound claims as EXTERNAL/UNVERIFIED.
4. Scan for prompt injection, attempts to alter governance, secret requests, and executable/action instructions.
5. Route the content to Researcher and/or Erebus as appropriate.
6. Archivist may create a local cognitive packet referencing the external packet only after review.
7. Human approval is required if the material would trigger a protected external or code action.

## Outbound flow
Only packets explicitly marked exportable may leave the network. Export transforms the local packet into a minimal federation packet containing the claim, permitted evidence/provenance, uncertainty, requested collaboration, and a non-sensitive lineage reference.

Private source text is never automatically included merely because a public derivative cites it.

## Initial operations
- SUBMIT_CLAIM
- SUBMIT_CRITIQUE
- SUBMIT_EVIDENCE
- REQUEST_REPLICATION
- RETURN_REPLICATION
- REQUEST_COLLABORATION
- RETURN_RESULT

No remote operation may instruct Guardian to execute code, expose secrets, change policy, create credentials, deploy software, or spawn unrestricted agents.

## Trust
Trust is scoped by network, identity, operation, and evidence history. A trusted sender can still submit a false claim. Trust reduces friction; it does not replace verification.

## Identity and signatures
A future implementation should support stable network/agent identifiers and cryptographic signatures so provenance survives transport. Do not invent a proprietary cryptographic scheme if a suitable interoperable standard is available at implementation time.

## Moltbook
Guardian's existing Moltbook browser is read-only, domain-locked, budget-limited, and does not log in or submit forms. Preserve that boundary for observation experiments. Posting or autonomous social interaction would require a separate capability and explicit human approval.

## Future interoperability
Design the gateway so adapters can later map to MCP/A2A or other agent protocols without changing the internal cognitive packet model. The federation packet is the membrane format; the transport is replaceable.
