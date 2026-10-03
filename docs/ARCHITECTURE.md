# MathLab architecture

MathLab treats a research project as a **handoff + durable blackboard + parallel research islands**.
The model context is disposable; the research state is not.

## Data flow

1. **Cartographer** ingests `HANDOFF.md` and seeds conservative claims/tasks.
2. **Director** allocates work across diverse islands.
3. Independent **research workers** use local shell, web search and structured blackboard tools.
4. Workers publish durable claims, computations, counterexamples and proof artifacts.
5. `PROVISIONAL_PROOF` claims automatically enter a fresh-context **Verifier** pipeline.
6. Periodic **Seminars** selectively migrate useful ideas across islands.
7. Agents can file **capability requests**. The RA framework engineer can hot-add project-local extension tools.
8. SQLite + project files survive crashes and model context resets.

## Why agents do not share one giant conversation

Independence is useful. A single attractive but false idea can otherwise anchor every worker. Agents communicate
through promoted findings, targeted messages and seminars. Messages are delivered opportunistically during tool
loops and persist if the recipient is not currently active.

## RA / self-extension

The RA writes tools to:

```
.mathlab/extensions/
    manifest.json
    my_tool.py
```

`manifest.json` entries look like:

```json
{
  "tools": {
    "my_tool": {
      "description": "What it does",
      "entrypoint": "my_tool.py"
    }
  }
}
```

Every extension receives JSON on stdin and emits JSON or text on stdout. `list_capabilities` and
`run_extension` re-read the manifest every invocation, so extensions are hot-loaded without restarting active
research. By default the RA may extend this layer but may not rewrite MathLab core.

## Evidence discipline

The blackboard status ladder is:

`IDEA → CONJECTURED → COMPUTATIONALLY_VERIFIED → PROVISIONAL_PROOF → INDEPENDENTLY_VERIFIED → FORMALLY_VERIFIED`

with `REFUTED` and `DISPUTED` side states. The distinction is enforced in the workflow rather than left entirely
to prose prompts.
