# agentic-loop-agent

A minimal example of the Claude Agent SDK's agentic loop, built from the
[Agent SDK quickstart](https://code.claude.com/docs/en/agent-sdk/quickstart).
The agent reads `utils.py` (which has two intentional bugs), finds the
issues, and fixes them autonomously using the `Read`, `Edit`, and `Glob`
tools.

## Setup

1. Install [uv](https://docs.astral.sh/uv/) if you don't have it:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. Install dependencies (already done if you're using this checked-out project):
   ```bash
   uv sync
   ```
3. Create your `.env` file from the example and fill in credentials for
   **one** of the two options below:
   ```bash
   cp .env.example .env
   ```

   - **Direct Anthropic API** — set `ANTHROPIC_API_KEY=sk-ant-...`. Get a key
     from the [Claude Console](https://platform.claude.com/).
   - **Claude Sonnet on Azure AI Foundry** — set `AZURE_FOUNDRY_ENDPOINT`,
     `AZURE_FOUNDRY_API_KEY`, and `AZURE_FOUNDRY_MODEL` (your deployment
     name). `agent.py` reads these and points the SDK at your Foundry
     resource as a plain Anthropic-compatible endpoint
     (`ANTHROPIC_BASE_URL` + `ANTHROPIC_API_KEY`, passed via
     `ClaudeAgentOptions.env`), **not** through the SDK's native
     `CLAUDE_CODE_USE_FOUNDRY` integration — so there's no Azure credential
     chain or `az login` involved, just the key/endpoint/model you copy from
     the Foundry portal's **Endpoints and keys** page.

   The SDK itself does not read `.env` files, so `agent.py` loads it at
   startup with `python-dotenv`. `.env` is git-ignored — never commit it.

## Running the agent

### Default mode: find and fix bugs

```bash
uv run agent.py
```

This sends the default prompt ("Review utils.py for bugs that would cause
crashes. Fix any issues you find.") with `allowed_tools=["Read", "Edit",
"Glob"]` and `permission_mode="acceptEdits"`, so file edits are auto-approved.
The agent reads `utils.py`, finds the division-by-zero bug in
`calculate_average` and the `None`-handling bug in `get_user_name`, and edits
the file to fix both. The run ends with `Done: success`, plus turn count and
cost if the SDK reports them.

Check what changed:

```bash
git diff utils.py
```

You can also pass a custom prompt as a CLI argument:

```bash
uv run agent.py "Add type hints to all functions in utils.py"
```

### Full-loop mode: write and run tests

```bash
uv run agent.py --with-tests
```

This adds `Bash` to `allowed_tools` and uses the prompt "Write pytest unit
tests for utils.py, run them, and fix any failures." The agent writes a test
file, runs `pytest` via the `Bash` tool, and iterates until the tests pass.

Every tool call (name + input) made in either mode is logged to `agent.log`
by a `PreToolUse` hook. The same hook blocks any Bash command containing
`rm -rf`, regardless of mode.

## How the agentic loop works

`query()` returns an async iterator that drives the loop: your prompt goes to
Claude, Claude decides which tool to call (e.g. `Read` to inspect `utils.py`),
the SDK executes that tool and feeds the result (the "observation") back to
Claude, and this repeats — reasoning, tool call, observation — until Claude
decides the task is done and the loop yields a final `ResultMessage`. The
`async for` loop in `agent.py` simply prints each message as it streams by:
`AssistantMessage` text blocks show Claude's reasoning, tool-use blocks show
which tool it's calling, and the `ResultMessage` reports the outcome
(`Done: <subtype>`) along with turn count and cost when available.
