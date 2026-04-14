# Autoresearch: Autonomous AI-Driven Research Loop

## Purpose

Autoresearch is an experiment in autonomous ML research workflows where an AI agent independently conducts experiments on a language model training setup. The agent modifies code, runs fixed-duration experiments, evaluates results via validation metrics, and keeps or discards changes in a continuous loop. Key innovation: agents operate entirely autonomously overnight, producing 100+ experiments while humans sleep.

## Core Loop: Planning/Execution/Reflection

**File: `program.md` (human-written instructions, ~180 lines)**
**Core training file: `train.py` (agent-modifiable, ~600 lines)**

### Pseudocode of the Experiment Loop

```
LOOP FOREVER:
  1. [INSPECT] Read git state (current branch, commit)
  2. [PLAN] Analyze current val_bpb and experimental opportunities
  3. [MODIFY] Edit train.py with new idea (architecture, hyperparams, optimizer)
  4. [COMMIT] git commit with description
  5. [EXECUTE] uv run train.py > run.log 2>&1 (fixed 5-minute budget via TIME_BUDGET=300)
  6. [MEASURE] Extract metrics: grep "^val_bpb:\|^peak_vram_mb:" run.log
  7. [EVALUATE]
     - If crash: read tail -n 50 run.log, attempt fix or discard
     - If improved (lower val_bpb): KEEP (git commit stays)
     - If equal/worse: DISCARD (git reset to pre-experiment state)
  8. [REFLECT] Log results to results.tsv (commit, val_bpb, memory_gb, status, description)
  9. Continue indefinitely until manually interrupted
```

### Key Functions (from `train.py`)

- **Termination check** (line 603): `if step > 10 and total_training_time >= TIME_BUDGET: break`
- **Metrics capture** (lines 612-620): `val_bpb = evaluate_bpb(model, tokenizer, DEVICE_BATCH_SIZE)`; `peak_vram_mb = torch.cuda.max_memory_allocated() / 1024 / 1024`
- **Scheduling/Adaptation** (lines 555-570): progress-based LR, muon momentum, weight decay

### from `prepare.py`

- **evaluate_bpb()** (lines 344-366): Computes validation metric by summing per-token cross-entropy losses normalized by token byte lengths.
- **TIME_BUDGET = 300** (line 31): 5-minute wall-clock budget.

## Prompting Patterns & Instruction Design

### System-Level Guidance: `program.md`

1. **Setup** (lines 1-28): agree on run tag, create branch, read files, init results.tsv
2. **Constraints** (lines 30-50): CAN modify train.py; CANNOT modify prepare.py, add deps, modify evaluation
3. **Experiment Loop** (lines 61-95): 9-step procedural loop with explicit git ops; autonomy directive "NEVER STOP... do NOT pause to ask the human"
4. **Output parsing** (lines 97-116): strict TSV log format, status values (keep, discard, crash)

### Key Prompting Techniques

- Scoped context: explicit file reading list
- Procedural clarity: numbered 9-step loop
- Constrained action space: train.py editable; prepare.py immutable
- Single objective: lowest val_bpb
- Autonomy empowerment
- Crash recovery rules (threshold = 10 min)

## Transferability to Claude Code Subagent Orchestration

### Pattern 1: Fixed-Budget Experimentation
Implement budget checks in subagent loop: abort if context window > threshold or after N iterations. RAG research can implement iteration limits; code exploration can have max-file-visit counts.

### Pattern 2: Immutable Harness / Mutable Payload
Separate evaluation/reflection logic from exploration logic; designate read-only system files vs. research working files. Keep CLAUDE.md and core tools immutable; agents modify retrieval queries, search strategies, or spec drafts.

### Pattern 3: Metric-Driven Keep/Discard
Binary success criterion determines git state. Define measurable success metrics (spec quality, coverage %, doc relevance) and auto-revert failed iterations.

### Pattern 4: Procedural Loop with Explicit Stopping
program.md defines the 9-step loop; agent runs indefinitely until convergence or interrupt. Implement loop orchestration in agent init.

### Pattern 5: Constraint-Based Action Space
Capability whitelisting in subagent init. RAG agent reads from org docs but cannot modify them.

## Gaps & Limitations

1. Single-metric optimization (val_bpb only) — fix via composite scoring
2. No meta-learning across experiments — fix via searchable experiment log
3. Implicit cost accounting — fix via explicit Pareto frontier tracking
4. Limited tool ecosystem — fix via web search, GitHub API, arXiv tool use
5. No uncertainty quantification — fix via confidence thresholds and HITL checkpoints

## Relevance to Soup Framework

**Relevance: 4/5**

**Strengths:** Autonomous loop architecture applies directly to code exploration + RAG research; program.md pattern maps cleanly to CLAUDE.md subagent orchestration; fixed-budget constraint scales to LLM token/time limits; metric-driven keep/discard ensures reproducible, reversible iteration.

**Weaknesses:** ML-specific (model training metrics); no multi-agent coordination; no cross-run knowledge reuse.

**Recommended adaptations for Soup:**
1. Implement results.tsv-style logging for all agent experiments
2. Add confidence/uncertainty metrics to agent decisions
3. Build searchable experiment history
4. Separate immutable evaluation harness from mutable working files (e.g., immutable spec evaluator, mutable spec drafts)
