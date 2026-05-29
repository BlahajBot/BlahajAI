"""Regression tests for sudo detection and sudo password handling."""

import json

import tools.terminal_tool as terminal_tool


def setup_function():
    terminal_tool._reset_cached_sudo_passwords()


def teardown_function():
    terminal_tool._reset_cached_sudo_passwords()
    if hasattr(terminal_tool, "set_approval_progress_callback"):
        terminal_tool.set_approval_progress_callback(None)
    if hasattr(terminal_tool, "_set_approval_context_cwd"):
        terminal_tool._set_approval_context_cwd(None)


def test_searching_for_sudo_does_not_trigger_rewrite(monkeypatch):
    monkeypatch.delenv("SUDO_PASSWORD", raising=False)
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)

    command = "rg --line-number --no-heading --with-filename 'sudo' . | head -n 20"
    transformed, sudo_stdin = terminal_tool._transform_sudo_command(command)

    assert transformed == command
    assert sudo_stdin is None


def test_printf_literal_sudo_does_not_trigger_rewrite(monkeypatch):
    monkeypatch.delenv("SUDO_PASSWORD", raising=False)
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)

    command = "printf '%s\\n' sudo"
    transformed, sudo_stdin = terminal_tool._transform_sudo_command(command)

    assert transformed == command
    assert sudo_stdin is None


def test_non_command_argument_named_sudo_does_not_trigger_rewrite(monkeypatch):
    monkeypatch.delenv("SUDO_PASSWORD", raising=False)
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)

    command = "grep -n sudo README.md"
    transformed, sudo_stdin = terminal_tool._transform_sudo_command(command)

    assert transformed == command
    assert sudo_stdin is None


def test_actual_sudo_command_uses_configured_password(monkeypatch):
    monkeypatch.setenv("SUDO_PASSWORD", "testpass")
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)

    transformed, sudo_stdin = terminal_tool._transform_sudo_command("sudo apt install -y ripgrep")

    assert transformed == "sudo -S -p '' apt install -y ripgrep"
    assert sudo_stdin == "testpass\n"


def test_actual_sudo_after_leading_env_assignment_is_rewritten(monkeypatch):
    monkeypatch.setenv("SUDO_PASSWORD", "testpass")
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)

    transformed, sudo_stdin = terminal_tool._transform_sudo_command("DEBUG=1 sudo whoami")

    assert transformed == "DEBUG=1 sudo -S -p '' whoami"
    assert sudo_stdin == "testpass\n"


def test_explicit_empty_sudo_password_tries_empty_without_prompt(monkeypatch):
    monkeypatch.setenv("SUDO_PASSWORD", "")
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")

    def _fail_prompt(*_args, **_kwargs):
        raise AssertionError("interactive sudo prompt should not run for explicit empty password")

    monkeypatch.setattr(terminal_tool, "_prompt_for_sudo_password", _fail_prompt)

    transformed, sudo_stdin = terminal_tool._transform_sudo_command("sudo true")

    assert transformed == "sudo -S -p '' true"
    assert sudo_stdin == "\n"


def test_cached_sudo_password_is_used_when_env_is_unset(monkeypatch):
    monkeypatch.delenv("SUDO_PASSWORD", raising=False)
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
    terminal_tool._set_cached_sudo_password("cached-pass")

    transformed, sudo_stdin = terminal_tool._transform_sudo_command("echo ok && sudo whoami")

    assert transformed == "echo ok && sudo -S -p '' whoami"
    assert sudo_stdin == "cached-pass\n"


def test_cached_sudo_password_isolated_by_session_key(monkeypatch):
    monkeypatch.delenv("SUDO_PASSWORD", raising=False)
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)

    monkeypatch.setenv("HERMES_SESSION_KEY", "session-a")
    terminal_tool._set_cached_sudo_password("alpha-pass")

    monkeypatch.setenv("HERMES_SESSION_KEY", "session-b")
    assert terminal_tool._get_cached_sudo_password() == ""

    monkeypatch.setenv("HERMES_SESSION_KEY", "session-a")
    assert terminal_tool._get_cached_sudo_password() == "alpha-pass"


def test_passwordless_sudo_skips_interactive_prompt_and_rewrite(monkeypatch):
    monkeypatch.delenv("SUDO_PASSWORD", raising=False)
    monkeypatch.delenv("TERMINAL_ENV", raising=False)
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")

    def _fail_prompt(*_args, **_kwargs):
        raise AssertionError(
            "interactive sudo prompt should not run when sudo -n already works"
        )

    monkeypatch.setattr(terminal_tool, "_prompt_for_sudo_password", _fail_prompt)
    monkeypatch.setattr(terminal_tool, "_sudo_nopasswd_works", lambda: True, raising=False)

    transformed, sudo_stdin = terminal_tool._transform_sudo_command("sudo whoami")

    assert transformed == "sudo whoami"
    assert sudo_stdin is None


def test_passwordless_sudo_probe_rechecks_local_terminal(monkeypatch):
    monkeypatch.delenv("TERMINAL_ENV", raising=False)
    calls = []

    class Result:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return Result(0 if len(calls) == 1 else 1)

    monkeypatch.setattr(terminal_tool.subprocess, "run", fake_run)

    assert terminal_tool._sudo_nopasswd_works() is True
    assert terminal_tool._sudo_nopasswd_works() is False
    assert len(calls) == 2
    assert calls[0][0] == ["sudo", "-n", "true"]
    assert calls[1][0] == ["sudo", "-n", "true"]


def test_passwordless_sudo_probe_is_disabled_for_nonlocal_terminal_env(monkeypatch):
    monkeypatch.setenv("TERMINAL_ENV", "docker")

    def _fail_run(*_args, **_kwargs):
        raise AssertionError("host sudo probe must not run for non-local terminal envs")

    monkeypatch.setattr(terminal_tool.subprocess, "run", _fail_run)

    assert terminal_tool._sudo_nopasswd_works() is False


def test_validate_workdir_allows_windows_drive_paths():
    assert terminal_tool._validate_workdir(r"C:\Users\Alice\project") is None
    assert terminal_tool._validate_workdir("C:/Users/Alice/project") is None


def test_validate_workdir_allows_windows_unc_paths():
    assert terminal_tool._validate_workdir(r"\\server\share\project") is None


def test_validate_workdir_blocks_shell_metacharacters_in_windows_paths():
    assert terminal_tool._validate_workdir(r"C:\Users\Alice\project; rm -rf /")
    assert terminal_tool._validate_workdir(r"C:\Users\Alice\project$(whoami)")
    assert terminal_tool._validate_workdir("C:\\Users\\Alice\\project\nwhoami")


def test_terminal_result_includes_smart_escalation_rationale_after_user_approval(monkeypatch):
    monkeypatch.setattr(
        terminal_tool,
        "_check_all_guards",
        lambda _command, _env_type: {
            "approved": True,
            "user_approved": True,
            "smart_escalated": True,
            "smart_approval_decision": "escalate",
            "description": "shell command via -c/-lc flag",
            "approval_reason": "The command performs network service probing.",
        },
    )

    result = json.loads(
        terminal_tool.terminal_tool(
            "printf ok",
            timeout=5,
            task_id="test-smart-escalation-terminal-note",
        )
    )

    assert result["exit_code"] == 0
    assert result["output"] == "ok"
    assert "required approval" in result["approval"]
    assert "smart approval escalated" in result["approval"]
    assert "network service probing" in result["approval"]


def test_terminal_blocked_result_includes_smart_deny_rationale(monkeypatch):
    monkeypatch.setattr(
        terminal_tool,
        "_check_all_guards",
        lambda _command, _env_type: {
            "approved": False,
            "smart_denied": True,
            "smart_approval_decision": "deny",
            "description": "recursive delete",
            "approval_reason": "The command could destroy project files.",
            "message": "BLOCKED by smart approval: recursive delete.",
        },
    )

    result = json.loads(
        terminal_tool.terminal_tool(
            "printf should-not-run",
            timeout=5,
            task_id="test-smart-deny-terminal-note",
        )
    )

    assert result["status"] == "blocked"
    assert "BLOCKED by smart approval" in result["error"]
    assert "denied by smart approval" in result["approval"]
    assert "destroy project files" in result["approval"]


def test_terminal_result_includes_smart_approve_rationale(monkeypatch):
    monkeypatch.setattr(
        terminal_tool,
        "_check_all_guards",
        lambda _command, _env_type: {
            "approved": True,
            "smart_approved": True,
            "smart_approval_decision": "approve",
            "description": "shell command via -c/-lc flag",
            "approval_reason": "The command only prints a fixed string.",
        },
    )

    result = json.loads(
        terminal_tool.terminal_tool(
            "printf ok",
            timeout=5,
            task_id="test-smart-approve-terminal-note",
        )
    )

    assert result["exit_code"] == 0
    assert "auto-approved by smart approval" in result["approval"]
    assert "prints a fixed string" in result["approval"]


def test_smart_approval_guard_emits_progress_event(monkeypatch):
    events = []

    def capture(event_type, tool_name=None, preview=None, args=None, **kwargs):
        events.append({
            "event_type": event_type,
            "tool_name": tool_name,
            "preview": preview,
            "args": args,
            "kwargs": kwargs,
        })

    monkeypatch.setattr(
        terminal_tool,
        "_check_all_guards_impl",
        lambda _command, _env_type, approval_callback=None, cwd=None: {
            "approved": True,
            "smart_approved": True,
            "smart_approval_decision": "approve",
            "description": "shell command via -c/-lc flag",
            "approval_reason": "The command only prints a fixed string.",
        },
    )

    terminal_tool.set_approval_progress_callback(capture)
    result = terminal_tool._check_all_guards("printf ok", "local")

    assert result["approved"] is True
    assert events == [
        {
            "event_type": "approval.judged",
            "tool_name": "terminal",
            "preview": None,
            "args": {
                "decision": "approve",
                "description": "shell command via -c/-lc flag",
                "reason": "The command only prints a fixed string.",
                "source": "smart_approval",
            },
            "kwargs": {},
        }
    ]


def test_deterministic_auto_approval_does_not_emit_progress_event(monkeypatch):
    events = []
    monkeypatch.setattr(
        terminal_tool,
        "_check_all_guards_impl",
        lambda _command, _env_type, approval_callback=None, cwd=None: {
            "approved": True,
            "auto_approved": True,
            "description": "read-only shell wrapper",
        },
    )

    terminal_tool.set_approval_progress_callback(lambda *args, **kwargs: events.append((args, kwargs)))
    result = terminal_tool._check_all_guards("printf ok", "local")

    assert result["approved"] is True
    assert events == []


def test_terminal_passes_effective_workdir_to_approval_context(monkeypatch, tmp_path):
    captured = {}

    def fake_guard(command, env_type, approval_callback=None, cwd=None):
        captured["cwd"] = cwd
        return {"approved": True, "message": None}

    monkeypatch.setattr(terminal_tool, "_check_all_guards_impl", fake_guard)

    result = json.loads(
        terminal_tool.terminal_tool(
            "printf ok",
            timeout=5,
            workdir=str(tmp_path),
            task_id="test-approval-context-workdir",
        )
    )

    assert result["exit_code"] == 0
    assert captured["cwd"] == str(tmp_path)

