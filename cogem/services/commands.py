from __future__ import annotations

import os
import subprocess
import json
from typing import Any, Dict, Tuple


def handle_pre_pipeline_command(task: str, ctx: Dict[str, Any]) -> Tuple[bool, bool]:
    """
    Handle slash commands that short-circuit before router/build pipeline.

    Returns:
    - handled: command matched and was handled
    - should_exit: caller should break the REPL loop
    """
    console = ctx["console"]
    Text = ctx["Text"]
    MUTED = ctx["MUTED"]
    TITLE = ctx["TITLE"]
    LOG_WARN = ctx["LOG_WARN"]
    LOG_ERR = ctx["LOG_ERR"]
    LOG_OK = ctx["LOG_OK"]
    section_rule = ctx["section_rule"]

    if task.strip().lower() in ("/exit", "/quit"):
        console.print()
        console.print(Text("Goodbye.", style=TITLE))
        return True, True

    if task.startswith("/codex/model"):
        rest = task[len("/codex/model") :].strip()
        models = ctx["models"]
        _codex_model = ctx["_codex_model"]
        if not rest:
            console.print(
                Text(
                    "Codex LLM — used for drafting and improving code (`codex exec -m …`). "
                    "Pick any model ID your Codex CLI supports (varies by account; e.g. o3, gpt-5, "
                    "or provider-specific names). Gemini is configured separately with /gemini/model.",
                    style=MUTED,
                )
            )
            console.print(
                Text(
                    f"  This session: {models.get('codex') or 'default (no -m)'}",
                    style=MUTED,
                )
            )
            console.print(
                Text(
                    f"  From startup (--codex-model / COGEM_CODEX_MODEL): {_codex_model or '(none)'}",
                    style=MUTED,
                )
            )
            console.print(
                Text(
                    "  Usage: /codex/model <MODEL_ID>   or   /codex/model reset",
                    style=MUTED,
                )
            )
            return True, False
        if rest.lower() == "reset":
            models["codex"] = _codex_model
            console.print(
                Text(
                    f"Codex LLM reset to: {models.get('codex') or 'default (no -m)'}",
                    style=TITLE,
                )
            )
            return True, False
        models["codex"] = rest
        console.print(Text(f"Codex LLM set to: {rest}", style=TITLE))
        return True, False

    if task.startswith("/gemini/model"):
        rest = task[len("/gemini/model") :].strip()
        models = ctx["models"]
        _gemini_model = ctx["_gemini_model"]
        if not rest:
            console.print(
                Text(
                    "Gemini LLM — used for review and final summary (`gemini -m …`). "
                    "Pick any model ID your Gemini CLI supports (e.g. gemini-2.5-pro, "
                    "gemini-2.5-flash). Codex is configured separately with /codex/model.",
                    style=MUTED,
                )
            )
            console.print(
                Text(
                    f"  This session: {models.get('gemini') or 'default (no -m)'}",
                    style=MUTED,
                )
            )
            console.print(
                Text(
                    f"  From startup (--gemini-model / COGEM_GEMINI_MODEL): {_gemini_model or '(none)'}",
                    style=MUTED,
                )
            )
            console.print(
                Text(
                    "  Usage: /gemini/model <MODEL_ID>   or   /gemini/model reset",
                    style=MUTED,
                )
            )
            return True, False
        if rest.lower() == "reset":
            models["gemini"] = _gemini_model
            console.print(
                Text(
                    f"Gemini LLM reset to: {models.get('gemini') or 'default (no -m)'}",
                    style=TITLE,
                )
            )
            return True, False
        models["gemini"] = rest
        console.print(Text(f"Gemini LLM set to: {rest}", style=TITLE))
        return True, False

    if task.startswith("/repo/info"):
        _repo_root = ctx["_repo_root"]
        root = _repo_root()
        console.print()
        section_rule("Repo info")
        console.print()
        console.print(Text(f"Repo root: {root}", style=MUTED))
        try:
            proc_inside = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                cwd=root,
            )
            inside = (proc_inside.stdout or "").strip().lower() == "true"
        except Exception:
            inside = False
        if not inside:
            console.print(
                Text(
                    "Git: not a git repository (or git unavailable).",
                    style=LOG_WARN,
                )
            )
            console.print()
            return True, False
        try:
            proc_branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                cwd=root,
            )
            branch = (proc_branch.stdout or "").strip() or "(unknown)"
            console.print(Text(f"Git branch: {branch}", style=MUTED))
        except Exception:
            pass
        try:
            proc_last = subprocess.run(
                ["git", "log", "-1", "--oneline"],
                capture_output=True,
                text=True,
                cwd=root,
            )
            last = (proc_last.stdout or "").strip()
            if last:
                console.print(Text(f"Last commit: {last}", style=MUTED))
        except Exception:
            pass
        try:
            proc_status = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=root,
            )
            status = (proc_status.stdout or "").strip()
            console.print(Text("Working tree status (git --porcelain):", style=MUTED))
            console.print(status or "(clean)")
        except Exception:
            pass
        console.print()
        return True, False

    if task.startswith("/test"):
        cmd = ctx["_select_test_cmd"]()
        console.print()
        section_rule("Tests")
        if not cmd:
            console.print(
                Text("No known test command for this repo type.", style=LOG_WARN)
            )
            console.print()
            return True, False
        rc, out, err = ctx["_run_local_command"](cmd, "tests")
        if out.strip():
            console.print(out.strip())
        if rc != 0 and (err or "").strip():
            console.print(Text(err.strip()[:2000], style=LOG_WARN))
        return True, False

    if task.startswith("/lint"):
        cmd = ctx["_select_lint_cmd"]()
        console.print()
        section_rule("Lint")
        if not cmd:
            console.print(
                Text("No known lint command for this repo type.", style=LOG_WARN)
            )
            console.print()
            return True, False
        rc, out, err = ctx["_run_local_command"](cmd, "lint")
        if out.strip():
            console.print(out.strip())
        if rc != 0 and (err or "").strip():
            console.print(Text(err.strip()[:2000], style=LOG_WARN))
        return True, False

    if task.startswith("/run"):
        rest = task[len("/run") :].strip()
        if not rest:
            console.print(Text("Usage: /run <command + args>", style=MUTED))
            return True, False
        rc, out, err = ctx["_run_local_command"](rest, "run")
        console.print()
        section_rule("Command output")
        if out.strip():
            console.print(out.strip())
        if (err or "").strip():
            console.print(Text((err or "").strip()[:2000], style=LOG_WARN))
        console.print()
        return True, False

    if task.startswith("/github/info"):
        rest = task[len("/github/info") :].strip()
        if not rest:
            console.print(
                Text(
                    "Usage: /github/info <https://github.com/owner/repo or owner/repo>",
                    style=MUTED,
                )
            )
            return True, False
        owner, repo, _clone_url = ctx["_parse_github_repo_ref"](rest)
        if not owner or not repo:
            console.print(
                Text("Could not parse GitHub repository reference.", style=LOG_WARN)
            )
            return True, False
        console.print()
        info = ctx["_github_repo_info"](owner, repo)
        section_rule("GitHub repository info")
        console.print()
        console.print(info)
        console.print()
        return True, False

    if task.startswith("/github/clone"):
        rest = task[len("/github/clone") :].strip()
        if not rest:
            console.print(
                Text(
                    "Usage: /github/clone <https://github.com/owner/repo or owner/repo> [dest]",
                    style=MUTED,
                )
            )
            return True, False
        parts = rest.split()
        ref = parts[0].strip()
        dest = parts[1].strip() if len(parts) > 1 else ""
        owner, repo, clone_url = ctx["_parse_github_repo_ref"](ref)
        if not owner or not repo or not clone_url:
            console.print(
                Text("Could not parse GitHub repository reference.", style=LOG_WARN)
            )
            return True, False
        target_dir = dest or repo
        if os.path.lexists(target_dir):
            console.print(Text(f"Target already exists: {target_dir}", style=LOG_WARN))
            return True, False
        ctx["ensure_run_permissions"]()
        if not ctx["run_permissions"].get("granted"):
            console.print(
                Text("Local command execution denied by user permission.", style=LOG_WARN)
            )
            console.print()
            return True, False
        proc = ctx["_run_with_ascii_progress"](
            "git clone",
            lambda: ctx["_run_proc"](["git", "clone", clone_url, target_dir], cwd=os.getcwd()),
        )
        if proc.returncode == 0:
            console.print(Text(f"Cloned {owner}/{repo} -> {target_dir}", style=LOG_OK))
        else:
            console.print(Text("Git clone failed.", style=LOG_ERR))
            if (proc.stderr or "").strip():
                clip = (proc.stderr or "").strip()[:1200]
                if len((proc.stderr or "").strip()) > 1200:
                    clip += "..."
                console.print(Text(clip, style=LOG_WARN))
        console.print()
        return True, False

    if task.startswith("/mcp/plugins"):
        from cogem.mcp_plugins import list_plugins

        names = list_plugins()
        section_rule("MCP plugins")
        console.print()
        if names:
            for n in names:
                console.print(f"- {n}")
        else:
            console.print(Text("No MCP plugins configured.", style=MUTED))
            console.print(
                Text(
                    "Set COGEM_MCP_<NAME>_CMD/ARGS (jira/sentry/datadog/dbschema) "
                    "or COGEM_MCP_PLUGINS_JSON.",
                    style=MUTED,
                )
            )
        console.print()
        return True, False

    if task.startswith("/mcp/tools"):
        rest = task[len("/mcp/tools") :].strip()
        if not rest:
            console.print(Text("Usage: /mcp/tools <plugin>", style=MUTED))
            return True, False
        from cogem.mcp_plugins import list_tools

        ok, out = list_tools(rest)
        section_rule(f"MCP tools: {rest}")
        console.print()
        if ok:
            console.print(out)
        else:
            console.print(Text(out, style=LOG_WARN))
        console.print()
        return True, False

    if task.startswith("/mcp/call"):
        rest = task[len("/mcp/call") :].strip()
        if not rest:
            console.print(
                Text("Usage: /mcp/call <plugin> <tool> [json-args]", style=MUTED)
            )
            return True, False
        parts = rest.split(maxsplit=2)
        if len(parts) < 2:
            console.print(
                Text("Usage: /mcp/call <plugin> <tool> [json-args]", style=MUTED)
            )
            return True, False
        plugin, tool = parts[0], parts[1]
        args_obj = {}
        if len(parts) >= 3 and parts[2].strip():
            try:
                args_obj = json.loads(parts[2].strip())
                if not isinstance(args_obj, dict):
                    console.print(Text("json-args must be a JSON object.", style=LOG_WARN))
                    return True, False
            except json.JSONDecodeError:
                console.print(Text("Invalid json-args JSON.", style=LOG_WARN))
                return True, False
        from cogem.mcp_plugins import call_tool

        ok, out = call_tool(plugin, tool, args_obj)
        section_rule(f"MCP call: {plugin}.{tool}")
        console.print()
        if ok:
            console.print(out or "(empty result)")
        else:
            console.print(Text(out, style=LOG_WARN))
        console.print()
        return True, False

    if task.startswith("/rag/search"):
        rest = task[len("/rag/search") :].strip()
        if not rest:
            console.print(Text("Usage: /rag/search <query>", style=MUTED))
            return True, False
        try:
            from cogem.vector_index import VectorIndexConfig, semantic_search_repo

            rows = semantic_search_repo(
                repo_root=ctx["_repo_root"](),
                task=rest,
                config=VectorIndexConfig(
                    enabled=True,
                    rebuild=bool(
                        os.environ.get("COGEM_VECTOR_REBUILD", "0").strip().lower()
                        in ("1", "true", "yes", "on")
                    ),
                    top_k=int(os.environ.get("COGEM_VECTOR_TOP_K", "8")),
                    max_chunk_chars=int(os.environ.get("COGEM_VECTOR_CHUNK_CHARS", "2500")),
                    max_context_chars=int(
                        os.environ.get("COGEM_AUTO_REPO_CONTEXT_MAX_CHARS", "8000")
                    ),
                ),
            )
        except Exception as e:
            section_rule("RAG search")
            console.print()
            console.print(Text(f"RAG unavailable: {e}", style=LOG_WARN))
            console.print(
                Text(
                    "Install optional deps: pip install \".[vector]\"",
                    style=MUTED,
                )
            )
            console.print()
            return True, False

        section_rule("RAG search results")
        console.print()
        if not rows:
            console.print(Text("No semantic matches found.", style=MUTED))
            console.print()
            return True, False
        shown = 0
        for r in rows:
            p = str(r.get("path", "")).strip()
            t = str(r.get("text", "")).strip()
            if not p or not t:
                continue
            shown += 1
            preview = "\n".join(t.splitlines()[:24]).strip()
            console.print(Text(f"### {p}", style=MUTED))
            console.print(preview)
            console.print()
            if shown >= int(os.environ.get("COGEM_VECTOR_TOP_K", "8")):
                break
        return True, False

    if task.startswith("/pdf"):
        rest = task[len("/pdf") :].strip()
        if not rest:
            console.print(
                Text(
                    "Usage: /pdf <text> [out.pdf]  OR  /pdf @path/to/file.txt [out.pdf]",
                    style=MUTED,
                )
            )
            console.print()
            return True, False
        tokens = ctx["_shlex_split_cmd"](rest)
        if not tokens:
            console.print(Text("Usage: /pdf <text> [out.pdf]", style=MUTED))
            console.print()
            return True, False
        desired_out = None
        if len(tokens) >= 2 and tokens[-1].lower().endswith(".pdf"):
            desired_out = tokens[-1]
            content_tokens = tokens[:-1]
        else:
            content_tokens = tokens
        body = ""
        if (
            len(content_tokens) == 1
            and content_tokens[0].startswith("@")
            and not content_tokens[0].startswith("@@")
        ):
            rel = content_tokens[0][1:]
            roots = ctx["_mention_roots_list"]()
            abs_p = ctx["_resolve_mention_path"](rel)
            if not abs_p or not ctx["_path_allowed_for_mention"](abs_p, roots):
                console.print(
                    Text(f"Could not read @ mention: {content_tokens[0]}", style=LOG_WARN)
                )
                console.print()
                return True, False
            try:
                max_b = max(
                    4096, int(os.environ.get("COGEM_AT_MAX_FILE_BYTES", "400000"))
                )
            except ValueError:
                max_b = 400000
            body = ctx["_read_file_for_mention"](abs_p, max_b)
        else:
            body = " ".join(content_tokens).strip()
        if not body:
            console.print(Text("No PDF content provided.", style=LOG_WARN))
            console.print()
            return True, False
        from cogem.pdf_tools import generate_pdf_from_text, pdf_path_for_text_request

        final_path, display_name = pdf_path_for_text_request(os.getcwd(), desired_out)
        roots = ctx["_mention_roots_list"]()
        final_abs = os.path.realpath(final_path)
        if not any(
            final_abs == os.path.realpath(r)
            or final_abs.startswith(os.path.realpath(r) + os.sep)
            for r in roots
        ):
            console.print(
                Text(
                    "Refusing to write PDF outside the allowed workspace.", style=LOG_WARN
                )
            )
            console.print()
            return True, False
        try:
            generate_pdf_from_text(body, final_path)
        except Exception as e:
            console.print(Text(f"PDF generation failed: {e}", style=LOG_ERR))
            console.print()
            return True, False
        console.print()
        section_rule("PDF generated")
        console.print(Text(f"Wrote: {display_name}", style=LOG_OK))
        console.print(Text("Generated PDFs are plain-text layout PDFs.", style=MUTED))
        console.print()
        return True, False

    return False, False

