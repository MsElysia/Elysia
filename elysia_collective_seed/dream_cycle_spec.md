# Collective Dream Cycle Specification

## Purpose
Extend Guardian's existing DreamEngine from individual reflection into periodic collective memory consolidation. A Dream Cycle proposes new cognitive packets and tasks; it never silently rewrites history or directly deploys changes.

## Inputs
- recent Collective Memory packets
- unresolved/disputed packets
- experiment outcomes
- agent routing/performance statistics
- stale claims due for revalidation
- a bounded sample of older related packets

Genesis Memory is read-only input when relevant.

## Passes

### 1. Contradiction scan
Find claims that cannot simultaneously be true. Emit relationship updates and question/critique packets.

### 2. Convergence scan
Detect independently produced packets expressing substantially similar conclusions. Record convergence without treating correlated model outputs as independent evidence unless they truly used independent sources/methods.

### 3. Cross-domain association
Search for useful relationships between otherwise distant packet clusters. Explorer may turn promising associations into hypotheses.

### 4. Orphan recovery
Identify unresolved high-value packets that received no adequate follow-up and route them for research, critique, or experimentation.

### 5. Failure-pattern analysis
Cluster failed experiments and rejected proposals to identify recurring causes rather than repeatedly rediscovering the same dead ends.

### 6. Staleness review
Find claims whose factual basis may have changed and emit revalidation tasks.

### 7. Organizational reflection
Analyze which agent-role combinations produce useful outcomes, where work is duplicated, and whether routing or reputation creates blind spots.

### 8. Synthesis candidates
Elysia may create draft synthesis packets linking the strongest new relationships. Drafts retain uncertainty and dissent.

## Outputs
Dream Cycle outputs are normal cognitive packets or routing recommendations with `provenance.source_type = experiment|collective`. They receive the same validation and review as waking work.

## Safety constraints
- no code deployment;
- no mutation execution;
- no new external permissions;
- no autonomous creation of public posts/messages;
- no deletion of Genesis or Collective Memory;
- no self-approval of proposals generated during the cycle.

## Existing Guardian mapping
The current DreamEngine already implements memory reflection, behavior analysis, optimization, planning, and persistent Dream records. During ZIP reconciliation, prefer adapting that engine with collective passes and packet output rather than creating a second dream subsystem.

## Evaluation
Track useful discoveries, duplicated/false associations, contradictions found, orphan recovery rate, subsequent packet survival, resource cost, and whether Dream Cycle outputs improve later task performance.
