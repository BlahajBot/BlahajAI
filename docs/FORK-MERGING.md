# Merging upstream into this fork

This is a **fork** of `NousResearch/hermes-agent` (remote `upstream`) with a large
local divergence (thousands of commits on `master`). Big upstream merges are the
single most dangerous operation here: a bad conflict resolution can **keep one
side of a conflict and silently drop the other**, and git records the dropped
commit as merged (it's an ancestor of HEAD) even though its content never landed.

## The failure mode to watch for

A one-time audit of the June/July 2026 merge (`911a66d38`) found **18 silent
drops across 6 files** this way — only 17 files had conflicts at all, so audit
every one. Four recurring shapes:

1. **Call site kept, definition dropped** — the most common and most dangerous.
   `py_compile` passes (the lookup is deferred), so it detonates only at runtime.
2. **Partial-hunk reversion** — one half of a hunk survives, the other reverts.
   E.g. a wrapper kept its new `has_host_access` parameter but the *call site*
   reverted to the no-arg form, silently defaulting a security flag to `False`.
3. **Source upgraded, paired test dropped (or vice-versa)** — when one commit
   touched both `src` and `tests`, the merge often took the fork's whole test
   blob and discarded the upstream test *additions* even though HEAD shipped the
   matching source change. Restore both halves together.
4. **Conflict resolved wholesale toward the fork side** — pure upstream
   *additions* to a region the fork never touched get dropped. These are never
   intentional overrides.

The classic drop (shape 1): the merge keeps a **call site** from one branch but
drops the **definition** from the other. Result: HEAD references a symbol that no
longer exists → the process crashes at runtime, not at merge time. Examples:

| Kept | Dropped | Blast radius |
|------|---------|--------------|
| `await self._start_secondary_profile_adapters()` + `except MultiplexConfigError` | the whole multiplex impl in `gateway/run.py` | **fatal** gateway restart loop |
| adapter call `telegram_menu_max_commands()` | the function in `hermes_cli/commands.py` | telegram menu failed every boot |
| (unchanged callers) | per-call cache-dir resolver in `gateway/platforms/base.py` | cross-profile data leak |

## Post-merge verification (do this every time, before declaring success)

Let `B`=merge-base, `P1`=fork side, `P2`=upstream side (`git log --format=%P -1 <merge>`
gives P1 P2; `git merge-base P1 P2` gives B).

1. **Find the conflict files** — drops only happen where *both* sides changed a file:
   ```bash
   comm -12 <(git diff --name-only $B $P1 | sort) <(git diff --name-only $B $P2 | sort)
   ```
   In the 911a66d38 merge this was only 17 files — audit every one.

2. **Three-way check each conflict file** for dropped upstream hunks:
   ```bash
   git diff $B $P2 -- FILE     # what upstream changed
   git diff $B $P1 -- FILE     # what the fork intentionally changed (regions the fork owns)
   git diff $P2 HEAD -- FILE   # upstream additions showing as DELETED here, in regions
                               # the fork did NOT touch above, are dropped hunks
   ```
   For every identifier upstream added, confirm it exists in HEAD and, if a
   definition is gone, that nothing still references it (orphan = the bug).

3. **Static integrity sweep** across all changed `.py`:
   ```bash
   git diff --name-only $B HEAD | grep '\.py$' | xargs -r venv/bin/python -m py_compile
   ```
   Then grep for orphaned imports — every `from X import Y` must resolve in `X`.

4. **Boot smoke test** — the definitive check. Restart the gateway and watch for
   `ImportError` / `AttributeError` / `NameError`:
   ```bash
   venv/bin/python -m hermes_cli.main gateway restart
   tail -f logs/errors.log logs/gateway-exit-diag.log   # exit-diag captures fatal startup crashes
   ```
   `logs/gateway-exit-diag.log` records `asyncio.run.exception` tracebacks even
   when the process restart-loops too fast to read `errors.log`.

5. **Run the affected test suites** (e.g. `uv run pytest tests/gateway/test_multiplex_*.py -q`).

## Restoring a dropped hunk

```bash
git log --oneline -S "<dropped_symbol>" --all -- <file>   # find the commit that added it
git show <commit> -- <file>                                # extract the hunk
git apply <patch>                                          # try clean apply first
```
The fork has diverged heavily, so `git apply` often fails on context — then
**adapt by hand** to the fork's current structure (match the fork's function
signatures, not upstream's). Verify with `py_compile` + the boot smoke test.

## Doing the merge more safely next time

- Resolve conflicts **hunk by hunk**; never bulk `checkout --ours/--theirs` a
  whole file. For a file the fork has NOT intentionally changed, prefer
  upstream's version; only keep fork content where the fork deliberately owns it.
- After resolving, run the **conflict-file list from step 1** and diff each
  against `$P2` before committing — catch drops at merge time, not in production.
- Salvage external/contributor work by cherry-pick/rebase so authorship survives
  (see AGENTS.md "Contribution Rubric").
