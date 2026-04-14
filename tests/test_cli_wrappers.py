"""Tests for cli_wrappers — subprocess mocked for determinism.

Covers structured JSON output for git, docker, and gh wrappers. Each test
invokes the Click command in-process via CliRunner with a patched
``run_cmd`` returning synthetic stdout/stderr — so we verify parsing and
JSON shape without needing the real binaries.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cli_wrappers import CmdResult
from cli_wrappers import docker as docker_wrap
from cli_wrappers import dotnet as dotnet_wrap
from cli_wrappers import gh as gh_wrap
from cli_wrappers import git as git_wrap
from cli_wrappers import node_pkg as node_wrap


def _ok(stdout: str = "", stderr: str = "", rc: int = 0) -> CmdResult:
    """Build a synthetic subprocess result."""
    return CmdResult(returncode=rc, stdout=stdout, stderr=stderr)


def _last_json(output: str) -> dict[str, Any]:
    """Extract the last JSON-looking line from stdout."""
    lines = [ln for ln in output.splitlines() if ln.strip()]
    assert lines, f"no output lines: {output!r}"
    return json.loads(lines[-1])


class TestGitWrap:
    """git-wrap: status, log, branch-list parsing."""

    def test_status_branch_and_files(self) -> None:
        """Porcelain -z output parses into structured files list."""
        # '## main...origin/main [ahead 1]' then two entries null-separated.
        porcelain = (
            "## main...origin/main [ahead 1]\x00"
            "M  src/a.py\x00"
            "?? new.txt\x00"
        )

        def fake_run(argv: list[str], **_: Any) -> CmdResult:
            assert argv[0] == "git"
            return _ok(porcelain)

        runner = CliRunner()
        with patch("cli_wrappers.git.run_cmd", side_effect=fake_run):
            result = runner.invoke(git_wrap.cli, ["status"])
        assert result.exit_code == 0, result.output
        payload = _last_json(result.output)
        assert payload["status"] == "ok"
        assert payload["branch"] == "main"
        assert payload["ahead"] == 1
        assert payload["behind"] == 0
        paths = [f["path"] for f in payload["files"]]
        assert "src/a.py" in paths and "new.txt" in paths

    def test_status_error_surfaces_structured(self) -> None:
        """Non-zero exit from git yields an error JSON with the code."""

        def fake_run(argv: list[str], **_: Any) -> CmdResult:
            # Raise the SoupWrapperError path via check=True + rc!=0.
            from cli_wrappers import SoupWrapperError

            raise SoupWrapperError("fatal: not a git repository", code=128)

        runner = CliRunner()
        with patch("cli_wrappers.git.run_cmd", side_effect=fake_run):
            result = runner.invoke(git_wrap.cli, ["status"])
        assert result.exit_code == 128
        payload = _last_json(result.output)
        assert payload["status"] == "error"
        assert payload["code"] == 128
        assert "not a git repository" in payload["message"]

    def test_log_parses_commits(self) -> None:
        """Log output using custom separators parses into a commit list."""
        # Match the format string used in git.py: %H<US>%an<US>%ae<US>%at<US>%s<RS>
        us, rs = "\x1f", "\x1e"
        line1 = us.join(["abc123", "Alice", "a@x.com", "1700000000", "feat: x"]) + rs
        line2 = us.join(["def456", "Bob", "b@x.com", "1700000100", "fix: y"]) + rs

        def fake_run(argv: list[str], **_: Any) -> CmdResult:
            return _ok(line1 + line2)

        runner = CliRunner()
        with patch("cli_wrappers.git.run_cmd", side_effect=fake_run):
            result = runner.invoke(git_wrap.cli, ["log", "--limit", "2"])
        assert result.exit_code == 0
        payload = _last_json(result.output)
        assert payload["count"] == 2
        assert payload["commits"][0]["sha"] == "abc123"
        assert payload["commits"][1]["author"] == "Bob"
        assert payload["commits"][0]["timestamp"] == 1700000000


class TestDockerWrap:
    """docker-wrap: ps output parsing."""

    def test_ps_parses_jsonlines(self) -> None:
        """``docker ps --format '{{json .}}'`` is parsed into a list."""
        ndjson = (
            '{"ID":"abc","Image":"nginx","Status":"Up 5 minutes","Names":"web"}\n'
            '{"ID":"def","Image":"postgres","Status":"Up 1 minute","Names":"db"}\n'
        )

        def fake_run(argv: list[str], **_: Any) -> CmdResult:
            assert argv[0] == "docker"
            assert "ps" in argv
            return _ok(ndjson)

        runner = CliRunner()
        with patch("cli_wrappers.docker.run_cmd", side_effect=fake_run):
            result = runner.invoke(docker_wrap.cli, ["ps"])
        assert result.exit_code == 0, result.output
        payload = _last_json(result.output)
        assert payload["status"] == "ok"
        assert payload["count"] == 2
        assert payload["containers"][0]["Image"] == "nginx"

    def test_build_failure_returns_error(self) -> None:
        """Non-zero build exit becomes structured error output."""

        def fake_run(argv: list[str], **_: Any) -> CmdResult:
            return _ok(stdout="... error ...", stderr="Step 5 failed", rc=1)

        runner = CliRunner()
        with patch("cli_wrappers.docker.run_cmd", side_effect=fake_run):
            result = runner.invoke(docker_wrap.cli, ["build", ".", "--tag", "x:1"])
        assert result.exit_code == 1
        payload = _last_json(result.output)
        assert payload["status"] == "error"
        assert payload["code"] == 1


class TestGhWrap:
    """gh-wrap: pr-list passes --json and parses the result."""

    def test_pr_list_parses_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gh's JSON output round-trips through our wrapper."""
        monkeypatch.setenv("GITHUB_TOKEN", "stub-token")
        payload_in = [
            {"number": 1, "title": "T1", "state": "OPEN", "url": "https://g/1"},
            {"number": 2, "title": "T2", "state": "OPEN", "url": "https://g/2"},
        ]

        def fake_run(argv: list[str], **_: Any) -> CmdResult:
            assert argv[0] == "gh"
            assert "--json" in argv
            return _ok(json.dumps(payload_in))

        runner = CliRunner()
        with patch("cli_wrappers.gh.run_cmd", side_effect=fake_run):
            result = runner.invoke(gh_wrap.cli, ["pr-list", "--limit", "5"])
        assert result.exit_code == 0, result.output
        payload = _last_json(result.output)
        assert payload["status"] == "ok"
        assert payload["count"] == 2
        assert payload["prs"][0]["number"] == 1


class TestPsqlSafety:
    """psql-wrap: write-guard heuristic blocks unsafe statements by default."""

    def test_insert_blocked_without_allow_write(self) -> None:
        """INSERT is rejected with exit code 3 unless --allow-write is set."""
        from cli_wrappers import psql as psql_wrap

        runner = CliRunner()
        result = runner.invoke(
            psql_wrap.cli, ["query", "INSERT INTO t VALUES (1)"]
        )
        assert result.exit_code == 3, result.output
        payload = _last_json(result.output)
        assert payload["status"] == "error"
        assert "write statement" in payload["message"].lower()

    def test_is_write_detects_ddl(self) -> None:
        """Heuristic flags DDL and DML; SELECT passes through."""
        from cli_wrappers.psql import _is_write

        assert _is_write("CREATE TABLE x (id int)")
        assert _is_write("  -- a comment\n DELETE FROM x WHERE 1=1")
        assert not _is_write("SELECT * FROM x")
        # ``/* UPDATE */`` is a comment and is stripped; outer query is
        # a SELECT -> read-only.
        assert not _is_write("/* UPDATE */ SELECT 1")


class TestPsqlGuardBypasses:
    """Cycle-1 C2: the write-guard must reject known bypass patterns."""

    def test_insert_hidden_after_line_comment_is_rejected(self) -> None:
        """``-- marker\\n INSERT ...`` — line comment stripper must not mask it."""
        from cli_wrappers import psql as psql_wrap

        runner = CliRunner()
        # ``--`` tells Click this is the positional SQL, not an option.
        result = runner.invoke(
            psql_wrap.cli,
            ["query", "--", "-- harmless\nINSERT INTO t VALUES (1)"],
        )
        assert result.exit_code == 3, result.output
        payload = _last_json(result.output)
        assert payload["status"] == "error"

    def test_insert_hidden_after_block_comment_is_rejected(self) -> None:
        """``/* ... */ INSERT`` — block comment stripper must not mask it."""
        from cli_wrappers import psql as psql_wrap

        runner = CliRunner()
        result = runner.invoke(
            psql_wrap.cli,
            ["query", "/* pretend I'm a SELECT */ DELETE FROM t"],
        )
        assert result.exit_code == 3, result.output

    def test_multi_statement_rejected_by_default(self) -> None:
        """Two statements separated by ``;`` require --allow-multi."""
        from cli_wrappers import psql as psql_wrap

        runner = CliRunner()
        result = runner.invoke(
            psql_wrap.cli,
            ["query", "SELECT 1; SELECT 2"],
        )
        assert result.exit_code == 3, result.output
        payload = _last_json(result.output)
        assert "multi-statement" in payload["message"].lower()

    def test_do_block_rejected_even_with_allow_write(self) -> None:
        """DO $$ ... $$ is always rejected — procedural code bypass."""
        from cli_wrappers import psql as psql_wrap

        runner = CliRunner()
        result = runner.invoke(
            psql_wrap.cli,
            [
                "query",
                "--allow-write",
                "--",
                "DO $$ BEGIN EXECUTE 'INS'||'ERT INTO t VALUES (1)'; END $$",
            ],
        )
        assert result.exit_code == 3, result.output
        payload = _last_json(result.output)
        assert "do $$" in payload["message"].lower()

    def test_pg_write_file_rejected_even_with_allow_write(self) -> None:
        """SELECT pg_write_file(...) is a side-effecting function."""
        from cli_wrappers import psql as psql_wrap

        runner = CliRunner()
        result = runner.invoke(
            psql_wrap.cli,
            [
                "query",
                "--allow-write",
                "SELECT pg_write_file('/tmp/x', 'data', false)",
            ],
        )
        assert result.exit_code == 3, result.output
        payload = _last_json(result.output)
        assert "pg_write_file" in payload["message"].lower() or (
            "side-effecting" in payload["message"].lower()
        )

    def test_copy_from_program_rejected(self) -> None:
        """COPY ... FROM PROGRAM is shell execution through Postgres."""
        from cli_wrappers import psql as psql_wrap

        runner = CliRunner()
        result = runner.invoke(
            psql_wrap.cli,
            [
                "query",
                "--allow-write",
                "COPY t FROM PROGRAM 'curl http://x' WITH (FORMAT csv)",
            ],
        )
        assert result.exit_code == 3, result.output

    def test_plpython_create_function_rejected(self) -> None:
        """CREATE FUNCTION ... LANGUAGE plpythonu is arbitrary code."""
        from cli_wrappers import psql as psql_wrap

        runner = CliRunner()
        result = runner.invoke(
            psql_wrap.cli,
            [
                "query",
                "--allow-write",
                "CREATE OR REPLACE FUNCTION f() RETURNS void "
                "AS $$ pass $$ LANGUAGE plpython3u",
            ],
        )
        assert result.exit_code == 3, result.output

    def test_insert_inside_cte_is_detected(self) -> None:
        """WITH x AS (INSERT ... RETURNING *) SELECT ... — CTE write."""
        from cli_wrappers import psql as psql_wrap

        runner = CliRunner()
        result = runner.invoke(
            psql_wrap.cli,
            [
                "query",
                "WITH x AS (INSERT INTO t VALUES (1) RETURNING *) "
                "SELECT * FROM x",
            ],
        )
        assert result.exit_code == 3, result.output

    def test_delete_in_second_statement_detected(self) -> None:
        """``SELECT 1; DELETE FROM t`` still has a writer; rejected even when
        --allow-multi would have allowed multiple statements."""
        from cli_wrappers import psql as psql_wrap

        runner = CliRunner()
        result = runner.invoke(
            psql_wrap.cli,
            ["query", "--allow-multi", "SELECT 1; DELETE FROM t"],
        )
        assert result.exit_code == 3, result.output

    def test_strip_comments_preserves_quoted_insert(self) -> None:
        """A quoted INSERT literal stays in-place after comment stripping."""
        from cli_wrappers.psql import _strip_comments

        out = _strip_comments("SELECT 'INSERT INTO' AS s -- trailing")
        # The quoted literal survives; the line comment is gone.
        assert "INSERT INTO" in out
        assert "trailing" not in out

    def test_split_statements_respects_dollar_quoted_semicolons(self) -> None:
        """Semicolons inside $$ bodies must not split statements."""
        from cli_wrappers.psql import _split_statements, _strip_comments

        sql = "SELECT 1; SELECT $$a;b;c$$"
        stmts = _split_statements(_strip_comments(sql))
        assert len(stmts) == 2
        assert "a;b;c" in stmts[1]

    def test_query_p_uses_parameter_binding(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``query-p`` passes --param values as psycopg params, not SQL."""
        from cli_wrappers import psql as psql_wrap

        captured: dict[str, Any] = {}

        class _FakeCursor:
            description: Any = None

            def __enter__(self) -> _FakeCursor:
                return self

            def __exit__(self, *exc: Any) -> None:
                return None

            def execute(
                self, sql: str, params: Any | None = None
            ) -> None:
                captured["sql"] = sql
                captured["params"] = params

            def fetchall(self) -> list[Any]:
                return []

            def __iter__(self) -> Any:
                return iter([])

        class _FakeConn:
            def cursor(self) -> _FakeCursor:
                return _FakeCursor()

            def close(self) -> None:
                return None

        monkeypatch.setattr(psql_wrap, "_connect", lambda autocommit=True: _FakeConn())
        runner = CliRunner()
        result = runner.invoke(
            psql_wrap.cli,
            [
                "query-p",
                "--sql",
                "SELECT * FROM t WHERE id = %s",
                "--param",
                "123",
            ],
        )
        assert result.exit_code == 0, result.output
        assert captured["sql"] == "SELECT * FROM t WHERE id = %s"
        assert captured["params"] == ("123",)

    def test_migrations_init_prints_sql_without_db(self) -> None:
        """``migrations-init --print-sql`` dumps the DDL and exits clean."""
        from cli_wrappers import psql as psql_wrap

        runner = CliRunner()
        result = runner.invoke(
            psql_wrap.cli, ["migrations-init", "--print-sql"]
        )
        assert result.exit_code == 0, result.output
        assert "schema_migrations" in result.output
        assert "CREATE TABLE IF NOT EXISTS" in result.output


class TestDotnetWrap:
    """dotnet-wrap: ef-script, ef-remove, ef-list, format."""

    def test_ef_script_forward_with_output(self) -> None:
        """``ef-script --from A --to B --output path`` wires positional args + --output."""
        captured: dict[str, Any] = {}

        def fake_run(argv: list[str], **_: Any) -> CmdResult:
            captured["argv"] = argv
            return _ok(stdout="-- SQL body --", stderr="")

        runner = CliRunner()
        with patch("cli_wrappers.dotnet.run_cmd", side_effect=fake_run):
            result = runner.invoke(
                dotnet_wrap.cli,
                [
                    "ef-script",
                    "--from",
                    "20260101_Init",
                    "--to",
                    "20260201_AddUsers",
                    "--idempotent",
                    "--output",
                    "migrate.sql",
                ],
            )
        assert result.exit_code == 0, result.output
        argv = captured["argv"]
        # Starts with dotnet ef migrations script
        assert argv[:4] == ["dotnet", "ef", "migrations", "script"]
        assert "20260101_Init" in argv
        assert "20260201_AddUsers" in argv
        assert "--idempotent" in argv
        assert "--output" in argv and "migrate.sql" in argv
        payload = _last_json(result.output)
        assert payload["status"] == "ok"
        assert payload["from"] == "20260101_Init"
        assert payload["to"] == "20260201_AddUsers"
        assert payload["idempotent"] is True
        assert payload["output"] == "migrate.sql"

    def test_ef_remove_force_flag(self) -> None:
        """``ef-remove --force`` invokes dotnet ef migrations remove --force."""
        captured: dict[str, Any] = {}

        def fake_run(argv: list[str], **_: Any) -> CmdResult:
            captured["argv"] = argv
            return _ok(stdout="Removing migration.", stderr="")

        runner = CliRunner()
        with patch("cli_wrappers.dotnet.run_cmd", side_effect=fake_run):
            result = runner.invoke(dotnet_wrap.cli, ["ef-remove", "--force"])
        assert result.exit_code == 0, result.output
        argv = captured["argv"]
        assert argv[:4] == ["dotnet", "ef", "migrations", "remove"]
        assert "--force" in argv
        payload = _last_json(result.output)
        assert payload["status"] == "ok"
        assert payload["force"] is True

    def test_ef_list_parses_json_envelope(self) -> None:
        """``ef-list --json`` extracts the ``//BEGIN .. //END`` JSON body."""
        migrations_json = (
            'Build started...\n'
            '//BEGIN\n'
            '[{"id":"20260101000000_InitialCreate","name":"InitialCreate","applied":true},'
            '{"id":"20260201000000_AddUsers","name":"AddUsers","applied":false}]\n'
            '//END\n'
            'Done.\n'
        )

        def fake_run(argv: list[str], **_: Any) -> CmdResult:
            # JSON mode should pass through to dotnet ef
            assert "--json" in argv
            return _ok(stdout=migrations_json, stderr="")

        runner = CliRunner()
        with patch("cli_wrappers.dotnet.run_cmd", side_effect=fake_run):
            result = runner.invoke(dotnet_wrap.cli, ["ef-list", "--json"])
        assert result.exit_code == 0, result.output
        payload = _last_json(result.output)
        assert payload["status"] == "ok"
        assert payload["count"] == 2
        assert payload["parsed"] is True
        assert payload["migrations"][0]["name"] == "InitialCreate"

    def test_format_verify_passes_verify_no_changes(self) -> None:
        """``format --verify`` implies --verify-no-changes for CI mode."""
        captured: dict[str, Any] = {}

        def fake_run(argv: list[str], **_: Any) -> CmdResult:
            captured["argv"] = argv
            return _ok(stdout="Formatting complete.", stderr="")

        runner = CliRunner()
        with patch("cli_wrappers.dotnet.run_cmd", side_effect=fake_run):
            result = runner.invoke(dotnet_wrap.cli, ["format", "--verify"])
        assert result.exit_code == 0, result.output
        argv = captured["argv"]
        assert argv[:2] == ["dotnet", "format"]
        assert "--verify-no-changes" in argv
        payload = _last_json(result.output)
        assert payload["status"] == "ok"
        assert payload["verify"] is True


class TestNodePkgWrap:
    """node-wrap: lockfile-based package-manager detection + argv shape."""

    def test_detect_pnpm_from_lockfile(self, tmp_path: Any) -> None:
        """``pnpm-lock.yaml`` -> pnpm (beats yarn/npm lockfiles if all present)."""
        (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
        (tmp_path / "yarn.lock").write_text("# yarn lockfile v1\n")
        (tmp_path / "package-lock.json").write_text("{}")
        assert node_wrap.detect_pm(tmp_path) == "pnpm"

    def test_detect_yarn_when_no_pnpm_lock(self, tmp_path: Any) -> None:
        """``yarn.lock`` alone -> yarn."""
        (tmp_path / "yarn.lock").write_text("# yarn lockfile v1\n")
        assert node_wrap.detect_pm(tmp_path) == "yarn"

    def test_detect_npm_default_when_no_lockfile(self, tmp_path: Any) -> None:
        """No lockfile at all -> npm (the default fallback)."""
        assert node_wrap.detect_pm(tmp_path) == "npm"

    def test_install_frozen_maps_to_npm_ci(self, tmp_path: Any) -> None:
        """npm + --frozen maps to ``npm ci`` (not ``npm install``)."""
        (tmp_path / "package-lock.json").write_text("{}")
        captured: dict[str, Any] = {}

        def fake_run(argv: list[str], **_: Any) -> CmdResult:
            captured["argv"] = argv
            return _ok(stdout="added 100 packages", stderr="")

        runner = CliRunner()
        with patch("cli_wrappers.node_pkg.run_cmd", side_effect=fake_run):
            result = runner.invoke(
                node_wrap.cli,
                ["install", "--frozen", "--cwd", str(tmp_path)],
            )
        assert result.exit_code == 0, result.output
        assert captured["argv"] == ["npm", "ci"]
        payload = _last_json(result.output)
        assert payload["status"] == "ok"
        assert payload["package_manager"] == "npm"
        assert payload["frozen"] is True

    def test_install_frozen_maps_to_pnpm_frozen_lockfile(self, tmp_path: Any) -> None:
        """pnpm + --frozen -> ``pnpm install --frozen-lockfile``."""
        (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
        captured: dict[str, Any] = {}

        def fake_run(argv: list[str], **_: Any) -> CmdResult:
            captured["argv"] = argv
            return _ok(stdout="Done", stderr="")

        runner = CliRunner()
        with patch("cli_wrappers.node_pkg.run_cmd", side_effect=fake_run):
            result = runner.invoke(
                node_wrap.cli,
                ["install", "--frozen", "--cwd", str(tmp_path)],
            )
        assert result.exit_code == 0, result.output
        assert captured["argv"] == ["pnpm", "install", "--frozen-lockfile"]
        payload = _last_json(result.output)
        assert payload["package_manager"] == "pnpm"

    def test_run_script_prepends_package_manager(self, tmp_path: Any) -> None:
        """``node-wrap run build`` on a yarn project -> ``yarn run build``."""
        (tmp_path / "yarn.lock").write_text("# yarn lockfile v1\n")
        captured: dict[str, Any] = {}

        def fake_run(argv: list[str], **_: Any) -> CmdResult:
            captured["argv"] = argv
            return _ok(stdout="built", stderr="")

        runner = CliRunner()
        with patch("cli_wrappers.node_pkg.run_cmd", side_effect=fake_run):
            result = runner.invoke(
                node_wrap.cli,
                ["run", "build", "--cwd", str(tmp_path)],
            )
        assert result.exit_code == 0, result.output
        assert captured["argv"] == ["yarn", "run", "build"]
        payload = _last_json(result.output)
        assert payload["package_manager"] == "yarn"
        assert payload["script"] == "build"
