"""Tests for project-level configuration files added in the agent governance PR.

Validates the following files (all new or modified in this PR):
- .env.example
- .gitignore
- .claudeignore / .cursorignore
- root Makefile
- backend/Makefile
- .cursor/rules/*.mdc
"""

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

# backend/tests/ -> backend/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (_REPO_ROOT / relative).read_text(encoding="utf-8")


def _lines(relative: str) -> list[str]:
    return _read(relative).splitlines()


def _parse_env_file(relative: str) -> dict[str, str]:
    """Return {KEY: value} for non-comment, non-blank lines in a .env-style file."""
    result: dict[str, str] = {}
    for raw in _lines(relative):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def _parse_mdc_frontmatter(path: Path) -> dict[str, str]:
    """Extract YAML frontmatter from an .mdc file into a {key: value} dict."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    block = match.group(1)
    result: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


# ---------------------------------------------------------------------------
# Module-level fixtures (no DB required — pure filesystem reads)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env_vars() -> dict[str, str]:
    return _parse_env_file(".env.example")


@pytest.fixture(scope="module")
def gitignore_lines() -> list[str]:
    return _lines(".gitignore")


@pytest.fixture(scope="module")
def cursorignore_content() -> str:
    return _read(".cursorignore")


@pytest.fixture(scope="module")
def claudeignore_content() -> str:
    return _read(".claudeignore")


@pytest.fixture(scope="module")
def root_makefile() -> str:
    return _read("Makefile")


@pytest.fixture(scope="module")
def backend_makefile() -> str:
    return _read("backend/Makefile")


@pytest.fixture(scope="module")
def mdc_files() -> list[Path]:
    return sorted((_REPO_ROOT / ".cursor" / "rules").glob("*.mdc"))


# ---------------------------------------------------------------------------
# .env.example
# ---------------------------------------------------------------------------


def test_env_example_exists() -> None:
    assert (_REPO_ROOT / ".env.example").is_file()


def test_env_example_contains_required_backend_vars(env_vars: dict[str, str]) -> None:
    required = {
        "DATABASE_URL",
        "REDIS_URL",
        "SECRET_KEY",
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "OPENAI_API_KEY",
        "ENVIRONMENT",
        "LOG_LEVEL",
    }
    missing = required - env_vars.keys()
    assert not missing, f"Missing backend env vars: {missing}"


def test_env_example_contains_required_frontend_vars(env_vars: dict[str, str]) -> None:
    required = {
        "NEXTAUTH_SECRET",
        "NEXTAUTH_URL",
        "NEXT_PUBLIC_API_URL",
        "NEXT_PUBLIC_WS_URL",
    }
    missing = required - env_vars.keys()
    assert not missing, f"Missing frontend env vars: {missing}"


def test_env_example_database_url_uses_asyncpg_driver(env_vars: dict[str, str]) -> None:
    assert env_vars["DATABASE_URL"].startswith("postgresql+asyncpg://"), (
        "DATABASE_URL must use the asyncpg async driver"
    )


def test_env_example_database_url_uses_host_port_5433(env_vars: dict[str, str]) -> None:
    # docker-compose maps Postgres host port 5433 -> container 5432
    assert ":5433/" in env_vars["DATABASE_URL"], (
        "DATABASE_URL should use port 5433 (docker-compose host-side port mapping)"
    )


def test_env_example_redis_url_uses_redis_scheme(env_vars: dict[str, str]) -> None:
    assert env_vars["REDIS_URL"].startswith("redis://")


def test_env_example_environment_defaults_to_development(env_vars: dict[str, str]) -> None:
    assert env_vars["ENVIRONMENT"] == "development"


def test_env_example_log_level_defaults_to_info(env_vars: dict[str, str]) -> None:
    assert env_vars["LOG_LEVEL"] == "INFO"


def test_env_example_secret_key_is_placeholder(env_vars: dict[str, str]) -> None:
    assert env_vars["SECRET_KEY"] == "change-me-in-production", (
        "SECRET_KEY in .env.example must be a placeholder, never a real secret"
    )


def test_env_example_nextauth_secret_is_placeholder(env_vars: dict[str, str]) -> None:
    assert env_vars["NEXTAUTH_SECRET"] == "change-me-in-production"


def test_env_example_openai_api_key_is_empty(env_vars: dict[str, str]) -> None:
    assert env_vars.get("OPENAI_API_KEY", "") == "", (
        "OPENAI_API_KEY must be empty in .env.example -- never commit real API keys"
    )


def test_env_example_oauth_credentials_are_empty(env_vars: dict[str, str]) -> None:
    for key in (
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
    ):
        assert env_vars.get(key, "") == "", (
            f"{key} must be empty in .env.example -- never commit OAuth credentials"
        )


def test_env_example_websocket_url_uses_ws_scheme(env_vars: dict[str, str]) -> None:
    assert env_vars["NEXT_PUBLIC_WS_URL"].startswith("ws://"), (
        "NEXT_PUBLIC_WS_URL must use ws:// scheme for WebSocket"
    )


def test_env_example_api_url_uses_http_scheme(env_vars: dict[str, str]) -> None:
    assert env_vars["NEXT_PUBLIC_API_URL"].startswith("http://")


def test_env_example_api_url_targets_localhost_8000(env_vars: dict[str, str]) -> None:
    assert env_vars["NEXT_PUBLIC_API_URL"] == "http://localhost:8000"


def test_env_example_nextauth_url_targets_localhost_3000(env_vars: dict[str, str]) -> None:
    assert env_vars["NEXTAUTH_URL"] == "http://localhost:3000"


def test_env_example_access_token_expire_minutes_is_integer(env_vars: dict[str, str]) -> None:
    raw = env_vars["ACCESS_TOKEN_EXPIRE_MINUTES"]
    assert raw.isdigit(), f"ACCESS_TOKEN_EXPIRE_MINUTES must be a positive integer, got: {raw!r}"


def test_env_example_access_token_expire_minutes_reasonable(env_vars: dict[str, str]) -> None:
    minutes = int(env_vars["ACCESS_TOKEN_EXPIRE_MINUTES"])
    # Must be between 1 minute and 30 days (43200 minutes)
    assert 1 <= minutes <= 43200, (
        f"ACCESS_TOKEN_EXPIRE_MINUTES={minutes} is outside reasonable range (1-43200)"
    )


def test_env_example_r2_bucket_has_default(env_vars: dict[str, str]) -> None:
    assert env_vars.get("R2_BUCKET") == "chat-engine-uploads"


def test_env_example_no_real_openai_key() -> None:
    content = _read(".env.example")
    assert not re.search(r"sk-[A-Za-z0-9]{20,}", content), (
        ".env.example must not contain a real OpenAI API key (sk-...)"
    )


def test_env_example_no_real_github_token() -> None:
    content = _read(".env.example")
    assert not re.search(r"ghp_[A-Za-z0-9]{36}", content)


def test_env_example_no_aws_access_key() -> None:
    content = _read(".env.example")
    assert not re.search(r"AKIA[A-Z0-9]{16}", content), (
        ".env.example must not contain an AWS access key (AKIA...)"
    )


# ---------------------------------------------------------------------------
# .gitignore
# ---------------------------------------------------------------------------


def test_gitignore_exists() -> None:
    assert (_REPO_ROOT / ".gitignore").is_file()


def test_gitignore_ignores_dotenv(gitignore_lines: list[str]) -> None:
    assert ".env" in gitignore_lines, ".env must be in .gitignore to prevent secret leaks"


def test_gitignore_ignores_dotenv_local(gitignore_lines: list[str]) -> None:
    assert ".env.local" in gitignore_lines


def test_gitignore_ignores_star_env_pattern(gitignore_lines: list[str]) -> None:
    assert "*.env" in gitignore_lines


def test_gitignore_explicitly_tracks_env_example(gitignore_lines: list[str]) -> None:
    """!.env.example negation was added in this PR to allow tracking the example file."""
    assert "!.env.example" in gitignore_lines, (
        "!.env.example must negate the *.env rule so the example file is tracked in git"
    )


def test_gitignore_ignores_notes_md(gitignore_lines: list[str]) -> None:
    """NOTES.md added in this PR for private agent state (per AI Coding research)."""
    assert "NOTES.md" in gitignore_lines, (
        "NOTES.md must be in .gitignore to exclude private agent notes"
    )


def test_gitignore_ignores_cursor_sessions(gitignore_lines: list[str]) -> None:
    """.cursor/sessions/ added in this PR."""
    assert ".cursor/sessions/" in gitignore_lines, (
        ".cursor/sessions/ must be ignored to exclude Cursor session state"
    )


def test_gitignore_ignores_pycache(gitignore_lines: list[str]) -> None:
    assert "__pycache__/" in gitignore_lines


def test_gitignore_ignores_node_modules(gitignore_lines: list[str]) -> None:
    assert "node_modules/" in gitignore_lines


def test_gitignore_ignores_venv(gitignore_lines: list[str]) -> None:
    assert ".venv/" in gitignore_lines


def test_gitignore_ignores_coverage_artifacts(gitignore_lines: list[str]) -> None:
    assert ".coverage" in gitignore_lines
    assert "htmlcov/" in gitignore_lines


def test_gitignore_negation_does_not_un_ignore_dotenv(gitignore_lines: list[str]) -> None:
    """The !.env.example line must not cancel the .env ignore rule."""
    assert ".env" in gitignore_lines, ".env must still be ignored"
    assert "!.env.example" in gitignore_lines, "negation for .env.example must be present"
    assert "!.env" not in gitignore_lines, (
        "!.env must NOT appear -- that would track real secrets"
    )


# ---------------------------------------------------------------------------
# .claudeignore and .cursorignore
# ---------------------------------------------------------------------------


def test_claudeignore_exists() -> None:
    assert (_REPO_ROOT / ".claudeignore").is_file()


def test_cursorignore_exists() -> None:
    assert (_REPO_ROOT / ".cursorignore").is_file()


def test_claudeignore_and_cursorignore_are_identical(
    claudeignore_content: str, cursorignore_content: str
) -> None:
    assert claudeignore_content == cursorignore_content, (
        ".claudeignore and .cursorignore must have identical content "
        "(both serve as token-discipline exclusion lists for different AI clients)"
    )


def test_ignore_files_have_same_line_count(
    claudeignore_content: str, cursorignore_content: str
) -> None:
    n_claude = len(claudeignore_content.splitlines())
    n_cursor = len(cursorignore_content.splitlines())
    assert n_claude == n_cursor, (
        f".claudeignore ({n_claude} lines) and .cursorignore ({n_cursor} lines) are out of sync"
    )


def test_ignore_files_exclude_uv_lock(cursorignore_content: str) -> None:
    assert "**/uv.lock" in cursorignore_content


def test_ignore_files_exclude_package_lock(cursorignore_content: str) -> None:
    assert "**/package-lock.json" in cursorignore_content


def test_ignore_files_exclude_yarn_lock(cursorignore_content: str) -> None:
    assert "**/yarn.lock" in cursorignore_content


def test_ignore_files_exclude_next_build(cursorignore_content: str) -> None:
    assert "**/.next/" in cursorignore_content


def test_ignore_files_exclude_dist(cursorignore_content: str) -> None:
    assert "**/dist/" in cursorignore_content


def test_ignore_files_exclude_build(cursorignore_content: str) -> None:
    assert "**/build/" in cursorignore_content


def test_ignore_files_exclude_pycache(cursorignore_content: str) -> None:
    assert "**/__pycache__/" in cursorignore_content


def test_ignore_files_exclude_venv(cursorignore_content: str) -> None:
    assert "**/.venv/" in cursorignore_content


def test_ignore_files_exclude_node_modules(cursorignore_content: str) -> None:
    assert "**/node_modules/" in cursorignore_content


def test_ignore_files_exclude_chat_plan(cursorignore_content: str) -> None:
    """chat-plan.md must be excluded to keep agent token counts low."""
    assert "chat-plan.md" in cursorignore_content


def test_ignore_files_exclude_png(cursorignore_content: str) -> None:
    assert "**/*.png" in cursorignore_content


def test_ignore_files_exclude_jpg(cursorignore_content: str) -> None:
    assert "**/*.jpg" in cursorignore_content


def test_ignore_files_exclude_svg(cursorignore_content: str) -> None:
    assert "**/*.svg" in cursorignore_content


def test_ignore_files_exclude_pdf(cursorignore_content: str) -> None:
    assert "**/*.pdf" in cursorignore_content


def test_ignore_files_exclude_alembic_sql_files(cursorignore_content: str) -> None:
    assert "**/alembic/versions/*.sql" in cursorignore_content


def test_ignore_files_exclude_test_results(cursorignore_content: str) -> None:
    assert "**/test-results/" in cursorignore_content


def test_ignore_files_exclude_playwright_report(cursorignore_content: str) -> None:
    assert "**/playwright-report/" in cursorignore_content


def test_ignore_files_do_not_exclude_python_sources(cursorignore_content: str) -> None:
    """The ignore file must not accidentally exclude Python source files."""
    lines = [
        ln.strip()
        for ln in cursorignore_content.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    prohibited = {"**/*.py", "src/", "backend/src/"}
    found = prohibited & set(lines)
    assert not found, f"Ignore file accidentally excludes Python sources: {found}"


# ---------------------------------------------------------------------------
# Root Makefile
# ---------------------------------------------------------------------------


def test_root_makefile_exists() -> None:
    assert (_REPO_ROOT / "Makefile").is_file()


def test_root_makefile_phony_declares_required_targets(root_makefile: str) -> None:
    phony_line = next(
        (ln for ln in root_makefile.splitlines() if ln.startswith(".PHONY:")), None
    )
    assert phony_line is not None, "Root Makefile must have a .PHONY declaration"
    declared = set(phony_line.replace(".PHONY:", "").split())
    required = {
        "install", "dev", "dev-backend", "dev-frontend",
        "test", "lint", "typecheck", "build", "clean",
    }
    missing = required - declared
    assert not missing, f"Root Makefile .PHONY missing targets: {missing}"


def test_root_makefile_install_delegates_to_backend(root_makefile: str) -> None:
    assert "$(MAKE) -C backend install" in root_makefile


def test_root_makefile_install_delegates_to_frontend(root_makefile: str) -> None:
    assert "$(MAKE) -C frontend install" in root_makefile


def test_root_makefile_dev_backend_uses_make_c_pattern(root_makefile: str) -> None:
    """Must delegate via $(MAKE) -C backend, not fragile 'cd backend && ...'."""
    assert "$(MAKE) -C backend run" in root_makefile


def test_root_makefile_dev_frontend_uses_make_c_pattern(root_makefile: str) -> None:
    assert "$(MAKE) -C frontend dev" in root_makefile


def test_root_makefile_test_delegates_to_backend(root_makefile: str) -> None:
    assert "$(MAKE) -C backend test" in root_makefile


def test_root_makefile_test_delegates_to_frontend(root_makefile: str) -> None:
    assert "$(MAKE) -C frontend test" in root_makefile


def test_root_makefile_lint_delegates_to_backend(root_makefile: str) -> None:
    assert "$(MAKE) -C backend lint" in root_makefile


def test_root_makefile_lint_delegates_to_frontend(root_makefile: str) -> None:
    assert "$(MAKE) -C frontend lint" in root_makefile


def test_root_makefile_typecheck_target_is_present(root_makefile: str) -> None:
    """typecheck target is new in this PR."""
    assert "typecheck:" in root_makefile


def test_root_makefile_typecheck_delegates_to_backend(root_makefile: str) -> None:
    assert "$(MAKE) -C backend typecheck" in root_makefile


def test_root_makefile_typecheck_delegates_to_frontend(root_makefile: str) -> None:
    assert "$(MAKE) -C frontend typecheck" in root_makefile


def test_root_makefile_clean_target_is_present(root_makefile: str) -> None:
    """clean target is new in this PR."""
    assert "clean:" in root_makefile


def test_root_makefile_clean_removes_backend_venv(root_makefile: str) -> None:
    assert "backend/.venv" in root_makefile


def test_root_makefile_clean_removes_frontend_next(root_makefile: str) -> None:
    assert "frontend/.next" in root_makefile


def test_root_makefile_build_delegates_to_frontend(root_makefile: str) -> None:
    assert "$(MAKE) -C frontend build" in root_makefile


def test_root_makefile_dev_runs_subprocesses_in_parallel(root_makefile: str) -> None:
    """dev target must run backend and frontend in parallel (-j2)."""
    assert "-j2" in root_makefile


def test_root_makefile_no_raw_cd_commands(root_makefile: str) -> None:
    """Root Makefile must not use 'cd <dir> &&' (replaced by $(MAKE) -C in this PR)."""
    suspicious = [
        ln for ln in root_makefile.splitlines()
        if "\tcd " in ln and not ln.strip().startswith("#")
    ]
    assert not suspicious, (
        f"Root Makefile must not use 'cd' delegation; use $(MAKE) -C. Found: {suspicious}"
    )


# ---------------------------------------------------------------------------
# backend/Makefile
# ---------------------------------------------------------------------------


def test_backend_makefile_exists() -> None:
    assert (_REPO_ROOT / "backend" / "Makefile").is_file()


def test_backend_makefile_phony_declares_required_targets(backend_makefile: str) -> None:
    phony_line = next(
        (ln for ln in backend_makefile.splitlines() if ln.startswith(".PHONY:")), None
    )
    assert phony_line is not None
    declared = set(phony_line.replace(".PHONY:", "").split())
    required = {
        "install", "run", "worker", "test",
        "lint", "format", "typecheck", "migrate", "migration", "seed",
    }
    missing = required - declared
    assert not missing, f"backend/Makefile .PHONY missing targets: {missing}"


def test_backend_makefile_install_uses_uv_sync(backend_makefile: str) -> None:
    """install target is new in this PR."""
    assert "uv sync" in backend_makefile


def test_backend_makefile_worker_uses_arq(backend_makefile: str) -> None:
    """worker target is new in this PR."""
    assert "uv run arq" in backend_makefile


def test_backend_makefile_worker_points_to_worker_settings(backend_makefile: str) -> None:
    assert "app.worker.main.WorkerSettings" in backend_makefile


def test_backend_makefile_format_calls_ruff_format(backend_makefile: str) -> None:
    """format target is new in this PR."""
    assert "ruff format" in backend_makefile


def test_backend_makefile_format_applies_autofix(backend_makefile: str) -> None:
    assert "ruff check --fix" in backend_makefile


def test_backend_makefile_migration_guards_empty_name(backend_makefile: str) -> None:
    """migration target is new in this PR -- must guard against missing name."""
    assert '[ -z "$(name)" ]' in backend_makefile, (
        'migration target must guard: @if [ -z "$(name)" ]; then exit 1; fi'
    )


def test_backend_makefile_migration_calls_alembic_autogenerate(backend_makefile: str) -> None:
    assert "alembic revision --autogenerate" in backend_makefile


def test_backend_makefile_migration_passes_name_param(backend_makefile: str) -> None:
    assert '-m "$(name)"' in backend_makefile


def test_backend_makefile_typecheck_uses_pyright(backend_makefile: str) -> None:
    assert "uv run pyright" in backend_makefile


def test_backend_makefile_lint_covers_both_src_and_tests(backend_makefile: str) -> None:
    assert "src/ tests/" in backend_makefile


def test_backend_makefile_test_uses_pytest(backend_makefile: str) -> None:
    assert "uv run pytest" in backend_makefile


def test_backend_makefile_run_sets_pythonpath_to_src(backend_makefile: str) -> None:
    assert "PYTHONPATH=src" in backend_makefile


def test_backend_makefile_migrate_uses_alembic_upgrade_head(backend_makefile: str) -> None:
    assert "alembic upgrade head" in backend_makefile


# ---------------------------------------------------------------------------
# .cursor/rules/*.mdc frontmatter
# ---------------------------------------------------------------------------


def test_cursor_rules_directory_exists() -> None:
    assert (_REPO_ROOT / ".cursor" / "rules").is_dir()


def test_all_expected_mdc_files_exist(mdc_files: list[Path]) -> None:
    expected = {
        "00-core.mdc",
        "10-backend.mdc",
        "11-backend-models.mdc",
        "12-backend-routers.mdc",
        "13-backend-tests.mdc",
        "20-frontend.mdc",
        "21-frontend-components.mdc",
        "30-infra.mdc",
        "40-workflow.mdc",
        "99-mdc-format.mdc",
    }
    actual = {f.name for f in mdc_files}
    missing = expected - actual
    assert not missing, f"Missing .mdc rule files: {missing}"


def test_all_mdc_files_start_with_frontmatter_delimiter(mdc_files: list[Path]) -> None:
    assert mdc_files, "No .mdc files found in .cursor/rules/"
    for path in mdc_files:
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), (
            f"{path.name} must start with YAML frontmatter (--- delimiter)"
        )


def test_all_mdc_files_have_nonempty_description(mdc_files: list[Path]) -> None:
    for path in mdc_files:
        fm = _parse_mdc_frontmatter(path)
        assert "description" in fm, f"{path.name}: frontmatter must include 'description'"
        assert fm["description"].strip(), f"{path.name}: 'description' must not be empty"


def test_all_mdc_files_have_always_apply_field(mdc_files: list[Path]) -> None:
    for path in mdc_files:
        fm = _parse_mdc_frontmatter(path)
        assert "alwaysApply" in fm, (
            f"{path.name}: frontmatter must include 'alwaysApply' field"
        )


def test_00_core_has_always_apply_true() -> None:
    core = _REPO_ROOT / ".cursor" / "rules" / "00-core.mdc"
    fm = _parse_mdc_frontmatter(core)
    assert fm.get("alwaysApply") == "true", (
        "00-core.mdc is the universal constitution -- alwaysApply must be true"
    )


def test_domain_specific_rules_have_always_apply_false(mdc_files: list[Path]) -> None:
    """Rules numbered 10+ are domain-specific and must never always apply."""
    for path in mdc_files:
        prefix = path.stem.split("-")[0]
        if not prefix.isdigit():
            continue
        if int(prefix) < 10:
            continue  # 00-09 range may be true
        fm = _parse_mdc_frontmatter(path)
        assert fm.get("alwaysApply") == "false", (
            f"{path.name}: domain-specific rules (10+) must have alwaysApply: false "
            "to avoid adding unrelated context to every prompt"
        )


def test_mdc_filenames_follow_nn_scope_convention(mdc_files: list[Path]) -> None:
    pattern = re.compile(r"^\d{2}-.+\.mdc$")
    for path in mdc_files:
        assert pattern.match(path.name), (
            f"{path.name}: must follow '<NN>-<scope>.mdc' naming convention"
        )


def test_00_core_mentions_tdd_rule() -> None:
    core = _REPO_ROOT / ".cursor" / "rules" / "00-core.mdc"
    assert "TDD" in core.read_text(), (
        "00-core.mdc must enforce TDD as a non-negotiable rule"
    )


def test_00_core_mentions_no_commits_to_main() -> None:
    core = _REPO_ROOT / ".cursor" / "rules" / "00-core.mdc"
    text = core.read_text()
    assert "main" in text.lower(), "00-core.mdc must mention branch protection (no commits to main)"


def test_backend_rule_globs_cover_backend_files() -> None:
    path = _REPO_ROOT / ".cursor" / "rules" / "10-backend.mdc"
    fm = _parse_mdc_frontmatter(path)
    assert "backend" in fm.get("globs", ""), (
        "10-backend.mdc globs must match backend Python files"
    )


def test_infra_rule_references_docker_compose() -> None:
    path = _REPO_ROOT / ".cursor" / "rules" / "30-infra.mdc"
    text = path.read_text()
    assert "docker-compose" in text, "30-infra.mdc must cover docker-compose files"


def test_backend_tests_rule_mentions_asyncio_mode() -> None:
    """13-backend-tests.mdc must clarify asyncio_mode = auto (no @pytest.mark.asyncio)."""
    path = _REPO_ROOT / ".cursor" / "rules" / "13-backend-tests.mdc"
    text = path.read_text()
    assert "asyncio_mode" in text, (
        "13-backend-tests.mdc should document asyncio_mode = auto setting"
    )


def test_workflow_rule_mentions_progress_file() -> None:
    path = _REPO_ROOT / ".cursor" / "rules" / "40-workflow.mdc"
    text = path.read_text()
    assert "PROGRESS.md" in text, (
        "40-workflow.mdc must reference PROGRESS.md as part of the claim/done workflow"
    )


def test_99_mdc_format_documents_always_apply_constraint() -> None:
    path = _REPO_ROOT / ".cursor" / "rules" / "99-mdc-format.mdc"
    text = path.read_text()
    assert "alwaysApply" in text, (
        "99-mdc-format.mdc must document alwaysApply constraint for rule authors"
    )


# ---------------------------------------------------------------------------
# Regression / boundary / negative tests
# ---------------------------------------------------------------------------


def test_env_example_all_keys_are_upper_snake_case(env_vars: dict[str, str]) -> None:
    pattern = re.compile(r"^[A-Z][A-Z0-9_]*$")
    invalid = [k for k in env_vars if not pattern.match(k)]
    assert not invalid, f"Env keys must be UPPER_SNAKE_CASE: {invalid}"


def test_env_example_file_is_tracked_by_git() -> None:
    """Regression: .env.example must exist as a file (proves git is tracking it)."""
    path = _REPO_ROOT / ".env.example"
    assert path.is_file()
    assert path.stat().st_size > 0, ".env.example must not be empty"


def test_backend_makefile_migration_exits_on_missing_name() -> None:
    """Regression: the exit 1 guard must be present, not just the message."""
    content = _read("backend/Makefile")
    # The guard: @if [ -z "$(name)" ]; then echo "..."; exit 1; fi
    assert "exit 1" in content, (
        "migration target must call 'exit 1' when name is missing"
    )


def test_mdc_rules_no_always_apply_true_on_domain_rules(mdc_files: list[Path]) -> None:
    """Inverse of the positive test: ensure NO domain rule has alwaysApply: true."""
    violations = []
    for path in mdc_files:
        prefix = path.stem.split("-")[0]
        if not prefix.isdigit() or int(prefix) < 10:
            continue
        fm = _parse_mdc_frontmatter(path)
        if fm.get("alwaysApply") == "true":
            violations.append(path.name)
    assert not violations, (
        f"Domain-specific rules must not have alwaysApply: true: {violations}"
    )


def test_cursorignore_has_at_least_forty_non_comment_lines(cursorignore_content: str) -> None:
    """Boundary: the ignore file should be substantive, not minimal."""
    non_comment = [
        ln for ln in cursorignore_content.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert len(non_comment) >= 40, (
        f"Ignore file only has {len(non_comment)} non-comment lines -- expected at least 40"
    )
