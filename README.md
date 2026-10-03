# MathLab

**MathLab is a persistent, multi-agent research lab for open-ended mathematics.**

Give it a research handoff, an OpenAI API key, and a sandboxed VM. It launches independent GPT-6 Astra research
workers, lets them use your local mathematical software, preserves claims/failures/computations in a durable
blackboard, independently referees candidate proofs, and shows the whole lab live in a terminal UI.

This is intentionally **not** a Lean-only theorem prover and **not** a group chat of role-playing agents. The core
loop is independent research islands + shared promoted artifacts + verification + selective communication.

## Quick start

Requirements: Python 3.11+ and an OpenAI API key. A Linux VM is recommended. Sage/PARI/Lean/LaTeX are optional.

```bash
unzip mathlab.zip
cd mathlab

python3 -m venv .venv
source .venv/bin/activate
pip install -e .

export OPENAI_API_KEY='...'

# Your handoff can be Markdown/text/TeX, or a PDF.
mathlab init zeta2-odd /path/to/HANDOFF.md
cd zeta2-odd

mathlab doctor
mathlab go
```

Or install the dev/test dependencies:

```bash
pip install -e '.[dev]'
pytest -q
```

### Resume

State is written continuously to `.mathlab/state.sqlite` and project files, so Ctrl-C/reboot is fine:

```bash
mathlab go
```

continues from the durable blackboard rather than starting the research from scratch.

## What happens after `mathlab go`

1. A **Cartographer** reads `HANDOFF.md` and extracts targets, definitions, known results, dead ends and open
   questions without silently promoting speculation to theorem.
2. A **Director** allocates a portfolio of tasks across independent research islands.
3. Astra workers reason, use local shell tools, write scripts, search the web, publish findings, and send targeted
   messages to other agents/islands.
4. Candidate proofs are marked `PROVISIONAL_PROOF` and automatically routed to a fresh-context **Verifier**.
5. Every few epochs a **Seminar** selectively cross-pollinates useful ideas without forcing all workers onto the
   same approach.
6. Missing capability? A worker calls `request_capability(...)`. The **RA framework engineer** can implement and
   test a hot-loadable extension while the research run continues.

## TUI

The default `mathlab go` launches a Textual interface showing:

- active/completed agents and their last substantive progress notes;
- streamed model research output and local shell commands/results;
- the current claim frontier with evidence status/confidence;
- capability requests and RA progress;
- estimated API spend.

Human steering commands are entered at the bottom:

```text
:msg A1234 Look again at the denominator normalization
:msg island:valuations Compare your result with C7f2c...
:focus C12ab34
:spawn 4 Try to disprove the claimed recurrence by exact computation
:pause
:resume
:stop
```

Any plain text is broadcast as a human note.

Run without the TUI if desired:

```bash
mathlab go --headless
```

## Local computation

MathLab uses OpenAI's Responses API `shell` tool in **local runtime** mode. The model requests shell commands;
MathLab runs them in the worker's persistent local workspace and returns stdout/stderr to the model.

Each normal worker starts in:

```text
.mathlab/workspaces/<agent-id>/
```

and receives environment variables:

```text
MATHLAB_PROJECT=/absolute/path/to/project
MATHLAB_WORKSPACE=/absolute/path/to/worker/workspace
```

So your VM can expose as much mathematical machinery as you want:

```text
Python / SymPy
SageMath
PARI/GP
python-flint
GAP
Z3
Lean 4 + Mathlib
LaTeX
custom C++/Rust programs
```

The VM itself is the sandbox. MathLab does not impose a shell allowlist in local mode.

## RA: research-framework self-extension

A researcher can submit:

```text
request_capability(
  title="Need a recurrence guesser",
  description="Given exact rational terms, guess a polynomial-coefficient recurrence...",
  acceptance_test="Correctly recover the recurrence for the supplied test sequence"
)
```

The RA is scheduled automatically. Its preferred extension mechanism is project-local and hot-loadable:

```text
.mathlab/extensions/
    manifest.json
    recurrence_guesser.py
```

Example manifest:

```json
{
  "tools": {
    "guess_recurrence": {
      "description": "Guess a P-recursive recurrence from exact terms",
      "entrypoint": "recurrence_guesser.py"
    }
  }
}
```

An extension reads a JSON object on stdin and writes JSON/text to stdout. Every `list_capabilities` or
`run_extension` call re-reads the manifest, so a running research session sees the new tool without restarting.

By default the RA may install packages and add extensions but **may not rewrite MathLab core**. You can change:

```toml
[ra]
enabled = true
allow_pip_install = true
allow_core_patch = false
```

`allow_core_patch` is deliberately off for v0.1: project-local tools genuinely hot-load; changes to the running
orchestrator itself are better staged and applied on restart rather than mutating Python code underneath active
async tasks.

## Evidence ladder

MathLab keeps these states separate:

```text
IDEA
CONJECTURED
COMPUTATIONALLY_VERIFIED
PROVISIONAL_PROOF
INDEPENDENTLY_VERIFIED
FORMALLY_VERIFIED
REFUTED
DISPUTED
```

Checking 10,000 cases therefore remains `COMPUTATIONALLY_VERIFIED`; it does not become a theorem because an
agent wrote confident prose around it.

## Agent communication

Agents do communicate, but MathLab avoids an unrestricted swarm chat. The main channels are:

- durable promoted findings on the blackboard;
- targeted `send_message` calls to an agent or `island:<name>`;
- explicit peer-review requests;
- periodic cross-island seminars.

Messages persist if a target is not active. During a worker's next tool loop, unread messages are delivered
opportunistically. This retains independent lines of attack while allowing high-value collaboration.

## Configuration

A freshly initialized project contains `mathlab.toml`. Useful knobs:

```toml
[model]
name = "gpt-6-astra"
reasoning = "max"
director_reasoning = "high"
verifier_reasoning = "max"
ra_reasoning = "high"

[research]
max_agents = 6
budget_usd = 200.0
tasks_per_epoch = 6
seminar_every = 4
worker_turn_limit = 18

[execution]
shell_timeout_s = 300
shell_max_output = 32000
enable_web_search = true
```

The spend shown in the TUI is an estimate from token usage using the Astra prices current when this release was
built. Your OpenAI dashboard remains the source of truth for billing.

## Project layout

```text
my-project/
├── HANDOFF.md
├── mathlab.toml
├── references/
├── code/
├── data/
├── artifacts/
└── .mathlab/
    ├── state.sqlite
    ├── workspaces/
    ├── extensions/
    └── logs/
```

The core package is intentionally problem-agnostic. A p-adic zeta project, combinatorics problem, functional
analysis problem, or experimental algebra project should differ primarily in its handoff, references and local
research tools—not in MathLab's orchestration code.

## Commands

```bash
mathlab init NAME HANDOFF.md
mathlab go [PROJECT]
mathlab go [PROJECT] --headless
mathlab status [PROJECT]
mathlab doctor
```

## Current scope / honest limitations

This is a functional **v0.1 research harness**, not a claim that autonomous open-problem research is solved.
In particular:

- The verifier is a fresh model context, not a mathematical oracle.
- `FORMALLY_VERIFIED` is a status the research workflow can use, but MathLab does not yet automatically invoke a
  generic Lean formalizer for every proof.
- Live inter-agent messages arrive at tool boundaries rather than interrupting a model in the middle of a long
  reasoning call.
- The RA hot-loads new project tools; arbitrary hot replacement of core orchestrator classes is intentionally not
  attempted while they are executing.
- Cost enforcement is checked between epochs/calls, so a single in-flight request can overshoot the configured
  budget slightly.

Those choices keep the core small enough to understand and modify while still supporting serious autonomous
research runs.

See `docs/ARCHITECTURE.md` for the internal design.
