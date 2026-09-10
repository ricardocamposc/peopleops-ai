"""Local viewer for Semantic Understanding experiment artifacts.

Usage:
    cd apps/peopleops-api
    PYTHONPATH=src poetry run python ../../evaluation/spikes/semantic_run_viewer.py

Then open http://127.0.0.1:8765 in a browser. The viewer reads JSON artifacts
under evaluation/runs and can append explicitly requested manual replays.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "evaluation" / "runs"
SPIKES_DIR = ROOT / "evaluation" / "spikes"
PEOPLEOPS_SRC = ROOT / "apps" / "peopleops-api" / "src"
PROMPT_TESTS_PREFIX = "semantic-prompt-playground-tests-"
PHASE_DIR_PATTERN = re.compile(r"^phase\d+(?:\.\d+)*$", re.IGNORECASE)
PROMPT_FILES = {
    "clarification": ROOT / "prompts" / "evaluations" / "prompt-clarificator.md",
}


def _ensure_project_imports() -> None:
    """Make the local application package available to the standalone viewer."""
    source = str(PEOPLEOPS_SRC)
    if source not in sys.path:
        sys.path.insert(0, source)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _phase412_case(case_id: str) -> dict | None:
    """Return benchmark expectations for an individual Phase 4.1.2 case."""
    cases_path = SPIKES_DIR / "direct_sqlalchemy_phase412_cases.jsonl"
    if not cases_path.is_file():
        return None
    for case in _read_jsonl(cases_path):
        if case.get("id") == case_id:
            return case
    return None


def _prompt_test_dirs() -> list[Path]:
    prompt_parent = RUNS_DIR / "phase42"
    return sorted(
        (
            path
            for path in prompt_parent.glob(f"{PROMPT_TESTS_PREFIX}*")
            if path.is_dir()
        ),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )


def _current_prompt_tests_dir() -> Path:
    """Return today's prompt-test folder, creating the next daily sequence."""
    date_key = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"{PROMPT_TESTS_PREFIX}{date_key}-"
    candidates = [path for path in _prompt_test_dirs() if path.name.startswith(prefix)]
    if candidates:
        return candidates[0]
    phase_dir = RUNS_DIR / "phase42"
    phase_dir.mkdir(parents=True, exist_ok=True)
    directory = phase_dir / f"{prefix}1"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _prompt_test_description(payload: dict) -> str:
    raw_input = payload.get("input") or payload.get("user_input")
    if isinstance(raw_input, str):
        try:
            raw_input = json.loads(raw_input)
        except json.JSONDecodeError:
            pass
    if isinstance(raw_input, dict):
        for key in ("original_user_request", "clarified_request_english", "question"):
            if raw_input.get(key):
                return str(raw_input[key])
    if raw_input:
        return str(raw_input)
    return str(payload.get("purpose") or payload.get("output_format") or "prompt test")


def _sync_prompt_tests_raw(directory: Path) -> None:
    """Write an index for prompt-test artifacts without duplicating payloads."""
    if not directory.is_dir():
        return

    rows: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        rows.append(
            {
                "artifact": path.name,
                "test_description": _prompt_test_description(payload),
                "timestamp": payload.get("timestamp"),
                "output_format": payload.get("output_format", "unknown"),
                "input_format": payload.get("input_format", "unknown"),
                "model": payload.get("model"),
            }
        )

    rows.sort(key=lambda row: str(row.get("timestamp", row["artifact"])))
    content = "".join(
        json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows
    )
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=directory, delete=False
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, directory / "raw_responses.jsonl")


def _phase_dirs() -> list[Path]:
    return sorted(
        (
            path
            for path in RUNS_DIR.iterdir()
            if path.is_dir() and PHASE_DIR_PATTERN.fullmatch(path.name)
        ),
        key=lambda path: tuple(
            int(part) for part in re.findall(r"\d+", path.name.lower())
        ),
    )


def _run_dirs(phase: str | None = None) -> list[Path]:
    parents = [RUNS_DIR / phase] if phase else _phase_dirs()
    return sorted(
        (
            path
            for parent in parents
            if parent.is_dir()
            for path in parent.iterdir()
            if path.is_dir()
        ),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )


def _phase_name(path: Path) -> str:
    try:
        return path.parent.relative_to(RUNS_DIR).as_posix()
    except ValueError:
        return "legacy"


def _safe_artifact_path(run_dir: Path, artifact: str) -> Path | None:
    candidate = (run_dir / artifact).resolve()
    try:
        candidate.relative_to(run_dir.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _safe_run_directory(relative_name: str) -> Path | None:
    """Resolve only a listed test directory below evaluation/runs."""
    raw_candidate = RUNS_DIR / relative_name
    if raw_candidate.is_symlink():
        return None
    candidate = raw_candidate.resolve()
    try:
        candidate.relative_to(RUNS_DIR.resolve())
    except ValueError:
        return None
    if not candidate.is_dir() or candidate.is_symlink():
        return None
    if candidate.parent == RUNS_DIR.resolve() and PHASE_DIR_PATTERN.fullmatch(candidate.name):
        return None
    if candidate.parent != RUNS_DIR.resolve() and not PHASE_DIR_PATTERN.fullmatch(candidate.parent.name):
        return None
    return candidate


def _read_run_rows(run_dir: Path) -> list[dict]:
    raw_path = run_dir / "raw_responses.jsonl"
    if not raw_path.exists():
        return []
    rows = _read_jsonl(raw_path)
    resolved: list[dict] = []
    for index_row in rows:
        artifact = index_row.get("artifact")
        artifact_path = _safe_artifact_path(run_dir, artifact) if artifact else None
        if artifact_path:
            try:
                payload = _read_json(artifact_path)
            except (OSError, json.JSONDecodeError):
                payload = dict(index_row)
            if isinstance(payload, dict):
                payload.setdefault("artifact", artifact)
                if index_row.get("test_description"):
                    payload.setdefault("test_description", index_row["test_description"])
                resolved.append(payload)
                continue
        resolved.append(index_row)
    return resolved


def _run_summary(path: Path) -> dict:
    raw_path = path / "raw_responses.jsonl"
    index_rows = _read_jsonl(raw_path) if raw_path.exists() else []
    manifest = _read_json(path / "manifest.json") if (path / "manifest.json").exists() else {}
    description = manifest.get("test_description") or next(
        (row.get("test_description") for row in index_rows if row.get("test_description")),
        None,
    )
    return {
        "name": path.name,
        "path": path.relative_to(RUNS_DIR).as_posix(),
        "phase": _phase_name(path),
        "test_description": description,
        "rows": sum(1 for _ in raw_path.open(encoding="utf-8"))
        if raw_path.exists()
        else 0,
        "created_at": datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
    }


def _reconstructed_prompts(row: dict) -> dict[str, str | None]:
    """Reconstruct Phase 4.1.2 prompts for old artifacts when possible."""
    if "clarification" not in row or "response" not in row:
        return {"clarifier": None, "generator": None}
    try:
        _ensure_project_imports()
        sys.path.insert(0, str(SPIKES_DIR))
        import direct_sqlalchemy_phase412 as phase412

        clarification = phase412.ClarificationResponse.model_validate(
            row["clarification"]
        )
        clarifier = (
            f"{phase412.CLARIFIER_PROMPT}\n\nUser request:\n{row['question']}"
        )
        generator = phase412.generator_prompt(
            question=row["question"], clarification=clarification
        )
        return {"clarifier": clarifier, "generator": generator}
    except (ImportError, KeyError, TypeError, ValueError):
        return {"clarifier": None, "generator": None}


def _enrich_phase44_events(row: dict) -> None:
    """Expose prompt/context fields for Phase 4.4 artifacts from any run version."""
    if row.get("mode") != "QUERY_PROGRAMMER_SUBGRAPH_ONLY":
        return
    programmer_metadata = row.get("programmer_metadata") or {}
    messages = programmer_metadata.get("messages") or []
    initial_messages = messages[:2]
    rendered_system_prompt = programmer_metadata.get("rendered_system_prompt")
    if not rendered_system_prompt:
        rendered_system_prompt = next(
            (
                message.get("content")
                for message in messages
                if isinstance(message, dict)
                and message.get("type") == "system"
                and message.get("content")
            ),
            None,
        )
    prompt_template = programmer_metadata.get("prompt_template")
    if not prompt_template:
        try:
            _ensure_project_imports()
            sys.path.insert(0, str(SPIKES_DIR))
            import direct_sqlalchemy_phase44 as phase44

            prompt_template = (
                phase44.PHASE44_QUERY_PROGRAMMER_PROMPT
            )
        except (ImportError, AttributeError):
            prompt_template = None
    for event in row.get("audit_trail", []):
        if event.get("role") != "query_programmer":
            continue
        event["prompt"] = event.get("prompt") or prompt_template
        event["prompt_template"] = event.get("prompt_template") or prompt_template
        event["rendered_system_prompt"] = (
            event.get("rendered_system_prompt") or rendered_system_prompt
        )
        # Older Phase 4.4 artifacts stored the final conversation here. The
        # first request should show only system prompt + functional input;
        # per-round accumulated context is shown by query_programmer_model.
        event["rendered_messages"] = initial_messages


def _run_payload(run_dir: Path) -> dict:
    manifest_path = run_dir / "manifest.json"
    metrics_path = run_dir / "metrics.json"
    rows = _read_run_rows(run_dir)
    for row in rows:
        reconstructed = _reconstructed_prompts(row)
        row["viewer_prompts"] = {
            "clarifier": row.get("clarifier_prompt") or reconstructed["clarifier"],
            "generator": row.get("generator_prompt") or reconstructed["generator"],
            "clarifier_persisted": "clarifier_prompt" in row,
            "generator_persisted": "generator_prompt" in row,
        }
        _enrich_phase44_events(row)
    return {
        "name": run_dir.name,
        "manifest": _read_json(manifest_path) if manifest_path.exists() else {},
        "metrics": _read_json(metrics_path) if metrics_path.exists() else {},
        "rows": rows,
    }


def _load_dotenv() -> None:
    """Load missing values from the project .env without displaying secrets."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _persist_manual_replay(
    run_dir: Path, case_id: str, repetition: int, replay: dict
) -> None:
    raw_path = run_dir / "raw_responses.jsonl"
    rows = _read_jsonl(raw_path)
    for row in rows:
        if row.get("id") == case_id and row.get("repetition") == repetition:
            artifact_path = _safe_artifact_path(run_dir, row.get("artifact", ""))
            if artifact_path:
                payload = _read_json(artifact_path)
                payload.setdefault("manual_replays", []).append(replay)
                artifact_path.write_text(
                    json.dumps(payload, ensure_ascii=False, default=str, indent=2)
                    + "\n",
                    encoding="utf-8",
                )
            else:
                row.setdefault("manual_replays", []).append(replay)
                content = "\n".join(
                    json.dumps(item, ensure_ascii=False, default=str) for item in rows
                ) + "\n"
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=run_dir, delete=False
                ) as temporary:
                    temporary.write(content)
                    temporary_path = Path(temporary.name)
                os.replace(temporary_path, raw_path)
            break
    else:
        raise KeyError(f"Case not found: {case_id}/{repetition}")


def _persist_playground_result(payload: dict) -> str:
    """Persist each manual prompt test as an independent JSON artifact."""
    run_dir = _current_prompt_tests_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_path = run_dir / f"prompt-test-{timestamp}-{uuid.uuid4().hex[:8]}.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, default=str, indent=2) + "\n",
        encoding="utf-8",
    )
    _sync_prompt_tests_raw(run_dir)
    return str(output_path.relative_to(ROOT))


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PeopleOps Semantic Run Viewer</title>
<style>
:root { color-scheme: dark; font-family: ui-sans-serif, system-ui, sans-serif; }
body { margin: 0; background: #111827; color: #e5e7eb; }
header { padding: 18px 24px; border-bottom: 1px solid #374151; }
main { display: grid; grid-template-columns: 300px 1fr; min-height: calc(100vh - 74px); }
aside { position: sticky; top: 0; align-self: start; height: 100vh; box-sizing: border-box; padding: 16px; border-right: 1px solid #374151; overflow-y: auto; }
section { padding: 18px 24px; overflow: auto; }
button, select, input { background: #1f2937; color: #e5e7eb; border: 1px solid #4b5563; border-radius: 6px; padding: 8px; }
button { cursor: pointer; width: auto; }
.run { display: block; width: 100%; text-align: left; margin: 6px 0; }
.run-row { display: flex; gap: 6px; align-items: stretch; margin: 6px 0; }
.run-row .run { flex: 1; margin: 0; }
.delete-run { width: 38px; padding: 6px; color: #fca5a5; font-size: 18px; }
.run.active { border-color: #60a5fa; background: #1e3a5f; }
.metrics-section { margin: 18px 0 22px; border: 1px solid #374151; border-radius: 8px; padding: 10px; }
.metrics-section > summary { cursor: pointer; font-size: 1.1rem; font-weight: 700; padding: 4px; }
.metrics-section h3 { margin: 14px 0 8px; }
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.cards { display: flex; gap: 10px; flex-wrap: wrap; margin: 14px 0; }
.card { background: #1f2937; border: 1px solid #374151; border-radius: 8px; padding: 10px 14px; min-width: 120px; }
.card b { display: block; font-size: 18px; color: #93c5fd; }
.summary-note { padding: 12px; background: #3b2f12; border: 1px solid #92701c; border-radius: 8px; margin: 12px 0; }
.case-status { display: flex; gap: 6px; flex-wrap: wrap; padding: 10px 0; }
.badge { border-radius: 12px; padding: 3px 8px; font-size: 12px; border: 1px solid #4b5563; }
.badge.ok { background: #12351f; } .badge.bad { background: #431b1b; }
.marker { margin-left: 8px; font-weight: 700; }
.marker.ok { color: #86efac; } .marker.warn { color: #fcd34d; } .marker.bad { color: #fca5a5; }
.case { border: 1px solid #374151; border-radius: 8px; margin: 10px 0; overflow: hidden; }
.case > summary { cursor: pointer; padding: 12px; background: #1f2937; }
.case-body { padding: 14px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.flow { display: flex; flex-direction: column; gap: 14px; margin: 12px 0; }
.node-group { border: 1px solid #334155; border-radius: 8px; padding: 6px 10px 10px; background: #0f172a; }
.node-group > summary { cursor: pointer; padding: 9px 10px; background: #1e293b; border-radius: 6px; font-weight: 700; color: #e2e8f0; }
.node-group > summary::marker { color: #93c5fd; }
.node-group-body { display: flex; flex-direction: column; gap: 14px; padding-top: 10px; }
.call-step { border-left: 3px solid #475569; padding-left: 12px; }
.call-step > summary { cursor: pointer; padding: 8px 10px; background: #1e293b; border-radius: 6px; font-weight: 700; }
.call-step > summary::marker { color: #93c5fd; }
.call-step > .step-body { padding-top: 8px; }
.call-step .panel { margin-top: 8px; }
.panel { background: #0f172a; border: 1px solid #334155; border-radius: 6px; overflow: hidden; }
.panel { display: flex; flex-direction: column; }
.panel h4 { margin: 0; padding: 8px 10px; background: #1e293b; }
pre, textarea { white-space: pre-wrap; word-break: break-word; padding: 10px; margin: 0; font-size: 12px; line-height: 1.45; }
.panel pre { flex: none; height: 120px; min-height: 80px; max-height: 70vh; overflow: auto; resize: vertical; }
.panel > button { align-self: flex-start; width: auto; margin: 8px 10px; }
textarea { box-sizing: border-box; width: 100%; height: 120px; min-height: 80px; max-height: 70vh; background: #0f172a; color: #e5e7eb; border: 0; resize: vertical; }
.copy-source { position: absolute; left: -10000px; width: 1px; height: 1px; opacity: 0; }
.editor { margin-top: 12px; }
.editor button { margin: 8px 8px 8px 0; }
.playground { max-width: 1100px; }
.playground label { display: block; margin: 12px 0; font-weight: 600; }
.playground input, .playground select { display: block; width: 100%; box-sizing: border-box; margin-top: 6px; }
.playground textarea { display: block; width: 100%; height: 120px; min-height: 80px; max-height: 70vh; box-sizing: border-box; margin-top: 6px; border: 1px solid #4b5563; border-radius: 6px; resize: vertical; }
.ok { color: #86efac; } .bad { color: #fca5a5; } .muted { color: #9ca3af; }
@media (max-width: 900px) { main { grid-template-columns: 1fr; } aside { border-right: 0; border-bottom: 1px solid #374151; } .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header><h2>PeopleOps Semantic Run Viewer</h2><div class="muted">Local view of evaluation/runs with individual prompt replay</div></header>
<main><aside><button onclick="loadRuns()">Refresh runs</button><button onclick="showPlayground()">Open generator tester</button><h3>Evaluation runs</h3><label class="filter">Phase <select id="run-filter" onchange="renderRuns()"><option value="all">All phases</option></select></label><div id="runs"></div></aside><section id="content"><p>Select a run.</p></section></main>
<script>
let runs = [];
let visibleRuns = [];
let phases = [];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const readableEscapes = value => String(value ?? '')
  .replace(/\\n/g, '\n')
  .replace(/\\r/g, '\r')
  .replace(/\\t/g, '\t');
const normalizeForDisplay = value => {
  if (Array.isArray(value)) return value.map(normalizeForDisplay);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => {
      if (key === 'content' && typeof item === 'string') {
        try { return [key, normalizeForDisplay(JSON.parse(item))]; }
        catch (_) { return [key, readableEscapes(item)]; }
      }
      return [key, normalizeForDisplay(item)];
    }));
  }
  return typeof value === 'string' ? readableEscapes(value) : value;
};
const pretty = x => {
  if (typeof x === 'string') {
    try { return JSON.stringify(normalizeForDisplay(JSON.parse(x)), null, 2); }
    catch (error) { return readableEscapes(x); }
  }
  return readableEscapes(JSON.stringify(normalizeForDisplay(x ?? null), null, 2));
};
function panel(title, value, note='', copyText=null, copyId='', copyLabel='', extraCopyText=null, extraCopyId='', extraCopyLabel='') { const copy = copyText === null ? '' : `<textarea class="copy-source" id="${esc(copyId)}">${esc(copyText)}</textarea><button type="button" onclick="copyHidden('${esc(copyId)}', this)">${esc(copyLabel || `Copy ${title.toLowerCase()}`)}</button>`; const extraCopy = extraCopyText === null ? '' : `<textarea class="copy-source" id="${esc(extraCopyId)}">${esc(extraCopyText)}</textarea><button type="button" onclick="copyHidden('${esc(extraCopyId)}', this)">${esc(extraCopyLabel)}</button>`; return `<div class="panel"><h4>${esc(title)} ${note ? `<span class="muted">(${esc(note)})</span>` : ''}</h4><pre>${esc(pretty(value))}</pre>${copy}${extraCopy}</div>`; }
async function loadRuns() {
  const [runResponse, phaseResponse] = await Promise.all([fetch('/api/runs'), fetch('/api/phases')]);
  runs = await runResponse.json();
  phases = await phaseResponse.json();
  const filter = document.getElementById('run-filter');
  const previous = filter.value;
  filter.innerHTML = `<option value="all">All phases</option>` + phases.map(p => `<option value="${esc(p.name)}">${esc(p.name)}</option>`).join('');
  if ([...filter.options].some(option => option.value === previous)) filter.value = previous;
  renderRuns();
}
function showPlayground() {
  document.getElementById('content').innerHTML = `<h2>Generator prompt tester</h2><div class="summary-note">This sends one independent structured request to the generator. The clarifier is shown only in stored run details; this tester defaults to SQLAlchemyGenerationResponse. Instructions and user input are sent through separate API fields. Each test is saved as its own JSON file under <code>evaluation/runs/phase42/semantic-prompt-playground-tests-YYYYMMDD-N/</code>. Use the <code>phase42</code> filter to inspect those folders.</div><div class="playground"><label>Model<input id="test-model" value="gpt-4o-mini"></label><label>Purpose (optional)<input id="test-purpose" value="semantic-prompt-playground"></label><label>Output format<select id="test-format" onchange="loadDefaultInstructions()"><option value="generation" selected>SQLAlchemyGenerationResponse (generator)</option><option value="clarification">ClarificationResponse (clarifier)</option></select></label><label>Instructions<textarea id="test-instructions" placeholder="Rules and context for the generator"></textarea><button type="button" onclick="copyTextarea('test-instructions', this)">Copy instructions</button></label><label>User input format<select id="test-input-format" onchange="toggleUserInput()"><option value="none">None</option><option value="json" selected>JSON</option><option value="text">Text</option></select></label><label>User input (optional)<textarea id="test-input" placeholder="Enter the clarifier JSON or the user's request"></textarea><button type="button" onclick="copyTextarea('test-input', this)">Copy user input</button></label><button onclick="sendTestPrompt()">Send generator prompt</button><div id="test-result"></div></div>`;
  loadDefaultInstructions();
}
async function showPromptTest(name) {
  const response = await fetch('/api/prompt-test?path=' + encodeURIComponent(name));
  const test = await response.json();
  if (!response.ok) { document.getElementById('content').innerHTML = `<span class="bad">${esc(test.error || 'Prompt test not found')}</span>`; return; }
  document.getElementById('content').innerHTML = `<h2>Prompt test</h2><div class="summary-note"><b>${esc(test.name)}</b> · ${esc(test.timestamp)} · ${esc(test.output_format)}</div><div class="grid">${panel('Instructions', test.instructions, '', test.instructions, 'prompt-test-instructions', 'Copy instructions')}${panel('Input', test.input, '', test.input || '', 'prompt-test-input', 'Copy input')}${panel('Output', test.response, '', JSON.stringify(test.response, null, 2), 'prompt-test-output', 'Copy response')}${panel('Metadata', {model: test.model, purpose: test.purpose, input_format: test.input_format})}</div>`;
}
async function loadDefaultInstructions() {
  const instructions = document.getElementById('test-instructions');
  if (!instructions || instructions.value.trim()) return;
  const format = document.getElementById('test-format').value;
  const response = await fetch('/api/prompt?format=' + encodeURIComponent(format));
  const data = await response.json();
  if (response.ok && !instructions.value.trim()) instructions.value = data.prompt;
}
async function copyTextarea(id, button) {
  const text = document.getElementById(id).value;
  await navigator.clipboard.writeText(text);
  const label = button.textContent;
  button.textContent = 'Copied';
  setTimeout(() => { button.textContent = label; }, 1200);
}
function toggleUserInput() {
  const input = document.getElementById('test-input');
  const disabled = document.getElementById('test-input-format').value === 'none';
  input.disabled = disabled;
  input.placeholder = disabled ? 'No user input will be sent' : 'Enter the clarifier JSON or the user\'s request';
}
async function sendTestPrompt() {
  const target = document.getElementById('test-result');
  target.innerHTML = '<p>Sending...</p>';
  const payload = {model: document.getElementById('test-model').value, purpose: document.getElementById('test-purpose').value, output_format: document.getElementById('test-format').value, instructions: document.getElementById('test-instructions').value, input_format: document.getElementById('test-input-format').value, user_input: document.getElementById('test-input').value};
  const response = await fetch('/api/test-prompt', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await response.json().catch(() => ({error: response.statusText}));
  target.innerHTML = response.ok ? `<div class="grid">${panel('Output', data.response, '', JSON.stringify(data.response, null, 2), 'test-output-copy', 'Copy response')}${panel('Request metadata', data.metadata)}${panel('Saved artifact', data.saved_artifact)}</div>` : `<span class="bad">${esc(data.error || 'Request failed')}</span>`;
}
function renderRuns() {
  const filter = document.getElementById('run-filter').value;
  visibleRuns = filter === 'all' ? runs : runs.filter(r => r.phase === filter);
  document.getElementById('runs').innerHTML = visibleRuns.map((r, i) => `<div class="run-row"><button class="run ${i===0?'active':''}" onclick="showRun(${i}, this)"><b>${esc(r.test_description || r.name)}</b><br><span class="muted">${esc(r.name)} · ${r.rows} filas · creado ${new Date(r.created_at).toLocaleString()}</span></button><button class="delete-run" title="Eliminar esta prueba" aria-label="Eliminar ${esc(r.name)}" onclick="deleteRun('${esc(r.path || r.name)}', '${esc(r.name)}', event)">🗑</button></div>`).join('') || '<p class="muted">No hay runs para este filtro.</p>';
  if (visibleRuns.length) {
    const first = document.querySelector('.run');
    if (visibleRuns[0].name.startsWith('semantic-prompt-playground-tests-')) showPromptRun(0, first);
    else if (visibleRuns[0].name.startsWith('semantic-clarifier-')) showClarifierRun(0, first);
    else showRun(0, first);
  }
}
async function deleteRun(path, name, event) {
  event.stopPropagation();
  if (!window.confirm(`¿Eliminar permanentemente la carpeta de prueba "${name}" y todos sus archivos?\n\n${path}`)) return;
  const response = await fetch('/api/run', {method: 'DELETE', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({path})});
  const data = await response.json().catch(() => ({error: response.statusText}));
  if (!response.ok) { window.alert(data.error || 'No se pudo eliminar la prueba.'); return; }
  document.getElementById('content').innerHTML = '<p class="muted">Prueba eliminada.</p>';
  await loadRuns();
}
async function showPromptRun(i, button) {
  document.querySelectorAll('.run').forEach(x => x.classList.remove('active')); if (button) button.classList.add('active');
  const data = await (await fetch('/api/run?name=' + encodeURIComponent(visibleRuns[i].path || visibleRuns[i].name))).json();
  const rows = data.rows || [];
  const runPath = visibleRuns[i].path || visibleRuns[i].name;
  document.getElementById('content').innerHTML = `<h2>${esc(data.name)}</h2><div class="summary-note">Prompt tester artifacts from this folder. Each row is one independent API call and preserves its complete instructions, input, and response.</div><div class="cards"><div class="card"><b>${rows.length}</b>Tests</div><div class="card"><b>${esc(data.name.slice(-2))}</b>Folder</div></div>${rows.map((r, n) => { const artifact = r.artifact || ''; const output = r.output_format || 'unknown'; const stamp = r.timestamp ? new Date(r.timestamp).toLocaleString() : 'unknown date'; let request = r.input || ''; try { const parsed = JSON.parse(request); if (parsed && typeof parsed === 'object') request = parsed.original_user_request || parsed.clarified_request_english || request; } catch (error) {} const status = r.response && r.response.status ? ` · ${r.response.status}` : ''; return `<button class="run" onclick="showPromptTest('${esc(runPath + '/' + artifact)}')"><b>${esc(request || r.test_description || 'Prompt test')}</b>${esc(status)}<br><span class="muted">${esc(stamp)} · ${esc(output)} · ${esc(artifact)}</span></button>`; }).join('') || '<p class="muted">No prompt tests found.</p>'}`;
}
function phase42Timeline(events) {
  if (!events || !events.length) return '<p class="muted">No call audit available.</p>';
  return `<div class="timeline">${events.map((event, index) => `<div class="panel"><h4>${index + 1}. ${esc(event.role || 'event')}</h4><pre>${esc(JSON.stringify({prompt: event.prompt, input: event.input, output: event.output, latency_ms: event.latency_ms}, null, 2))}</pre></div>`).join('')}</div>`;
}
async function showClarifierRun(i, button) {
  document.querySelectorAll('.run').forEach(x => x.classList.remove('active')); if (button) button.classList.add('active');
  const data = await (await fetch('/api/run?name=' + encodeURIComponent(visibleRuns[i].path || visibleRuns[i].name))).json();
  const rows = data.rows || [];
  const needs = rows.filter(r => r.response && r.response.needs_clarification).length;
  document.getElementById('content').innerHTML = `<h2>${esc(data.name)}</h2><div class="summary-note">Functional Analyst / Semantic Clarifier tests. These calls do not generate or validate SQLAlchemy queries.</div><div class="cards"><div class="card"><b>${rows.length}</b>Cases</div><div class="card"><b>${needs}/${rows.length}</b>Needs clarification</div><div class="card"><b>${esc(data.manifest && data.manifest.prompt_version || '')}</b>Prompt version</div></div>${rows.map((r, n) => { const response = r.response || {}; const needsClarification = Boolean(response.needs_clarification); const statusClass = needsClarification ? 'bad' : 'ok'; const suffix = `clarifier-${esc(r.id)}-${n}`; return `<details class="case" ${n===0?'open':''}><summary><b>${esc(r.id)}</b> · ${esc(r.question)} <span class="marker ${statusClass}">${needsClarification ? '!' : '✓'} ${needsClarification ? 'NEEDS_CLARIFICATION' : 'CLARIFIED'}</span></summary><div class="case-body"><div class="case-status"><span class="badge ${needsClarification ? 'bad':'ok'}">Needs clarification: ${needsClarification ? 'YES':'NO'}</span><span class="badge">Latency: ${esc(r.latency_ms)} ms</span></div><div class="grid">${panel('Question', r.question, '', r.question, `${suffix}-question`, 'Copy question')}${panel('Prompt', r.prompt, '', r.prompt, `${suffix}-prompt`, 'Copy prompt')}${panel('Input', r.input, '', JSON.stringify(r.input, null, 2), `${suffix}-input`, 'Copy input')}${panel('Response', response, '', JSON.stringify(response, null, 2), `${suffix}-response`, 'Copy response')}${panel('Metadata', r.metadata)}</div></div></details>`; }).join('') || '<p class="muted">No clarifier tests found.</p>'}`;
}
async function showPhase42RunLegacy(i, button) {
  document.querySelectorAll('.run').forEach(x => x.classList.remove('active')); if (button) button.classList.add('active');
  const data = await (await fetch('/api/run?name=' + encodeURIComponent(visibleRuns[i].path || visibleRuns[i].name))).json();
  const rows = data.rows || []; const m = data.metrics || {}; const productionSmoke = rows[0] && rows[0].mode === 'PRODUCTION_QUERY_PROGRAMMER_SUBGRAPH';
  const mode = rows[0] && rows[0].mode ? rows[0].mode : 'mixed';
  const approved = rows.filter(r => r.final_status === 'APPROVED').length;
  const technical = rows.filter(r => r.technical_valid).length;
  document.getElementById('content').innerHTML = `<h2>${esc(data.name)}</h2><div class="summary-note">Phase 4.2 audit. Technical validity and Senior approval are shown separately; compilation alone does not establish semantic correctness.</div>${phase42MetricCards(data.metrics, mode, rows)}${rows.map((r, n) => { const finalStatus = r.final_status || 'UNRESOLVED'; const ok = finalStatus === 'APPROVED' || finalStatus === 'QUERY_DEVELOPER_ONLY_COMPLETE'; const statusClass = ok ? 'ok' : 'bad'; const attempts = r.query_developer_attempts || []; const reviews = r.senior_reviews || []; return `<details class="case" ${n===0?'open':''}><summary><b>${esc(r.id)}</b> · ${esc(r.mode)} · ${esc(r.question)} <span class="marker ${statusClass}">${ok ? '✓' : '✖'} ${esc(finalStatus)}</span></summary><div class="case-body"><div class="case-status"><span class="badge">Query Programmer attempts: ${attempts.length}</span><span class="badge ${r.technical_valid ? 'ok':'bad'}">Technical: ${r.technical_valid ? 'OK':'FAIL'}</span><span class="badge ${reviews.some(x => x.status === 'APPROVED') ? 'ok':'bad'}">Senior reviews: ${reviews.length}</span></div><div class="grid">${panel('Functional Analyst', r.functional_analysis)}${panel('Query task', r.query_task)}${panel('Query Programmer attempts', attempts)}${panel('Validation', {first_pass: r.first_pass_validation, final: r.final_validation})}${panel('Senior reviews', reviews)}${phase42Timeline(r.audit_trail)}${panel('Final status', finalStatus)}${panel('Duration (ms)', r.duration_ms)}</div></div></details>`; }).join('') || '<p class="muted">No Phase 4.2 cases found.</p>'}`;
}
function phase44ToolPanel(step, event) {
  const base = `phase44-${step}-${Math.random().toString(36).slice(2)}`;
  const tool = event.tool_name || event.tool || 'application tool';
  const round = event.round == null ? '' : ` · model round ${event.round}`;
  return `<details class="call-step"><summary>Step ${step}: ${esc(tool)}${esc(round)}</summary><div class="step-body"><div class="muted">Executed by the application after an LLM tool call.</div>${panel('Tool input', event.input, '', JSON.stringify(event.input ?? null, null, 2), `${base}-input`, 'Copy tool input')}${panel('Tool output', event.output, '', JSON.stringify(event.output ?? null, null, 2), `${base}-output`, 'Copy tool output')}</div></details>`;
}
function phase44ModelPanel(step, event) {
  const base = `phase44-model-${step}-${Math.random().toString(36).slice(2)}`;
  const round = event.round == null ? '' : ` · model round ${event.round}`;
  const actor = event.role === 'senior_query_reviewer' ? 'Senior Reviewer LLM' : 'Query Programmer LLM';
  return `<details class="call-step"><summary>Step ${step}: ${actor}${esc(round)}</summary><div class="step-body"><div class="muted">The input is separated into the new messages for this call and the complete accumulated context.</div>${panel('Prompt template', event.prompt_template, '', event.prompt_template || '', `${base}-prompt`, 'Copy prompt')}${panel('Rendered system prompt', event.rendered_system_prompt, '', event.rendered_system_prompt || '', `${base}-rendered-prompt`, 'Copy rendered prompt')}${panel('Input de esta llamada', event.incremental_input, '', JSON.stringify(event.incremental_input ?? null, null, 2), `${base}-incremental-input`, 'Copy input')}${panel('Contexto completo enviado al LLM', event.input, '', JSON.stringify(event.input ?? null, null, 2), `${base}-input`, 'Copy full context')}${panel('LLM response', event.output, '', JSON.stringify(event.output ?? null, null, 2), `${base}-output`, 'Copy LLM response')}</div></details>`;
}
function phase44NodeForEvent(event) {
  return event.graph_node || 'unassigned';
}
function phase44NodeLabel(node) {
  const labels = {received: 'received', workflow: 'workflow', understand_request: 'understand_request · Functional Analyst', discover_catalog: 'discover_catalog', plan_queries: 'plan_queries · Query Programmer subgraph', senior_review_node: 'senior_review_node · Senior Reviewer', execute_queries: 'execute_queries', retrieve_policy: 'retrieve_policy', hr_assistant: 'hr_assistant · HR Assistant subgraph', finalize_response: 'finalize_response', human_review: 'human_review', unassigned: 'unassigned · event without graph_node'};
  return labels[node] || node;
}
function phase44GroupedFlow(events, caseId) {
  const groups = [];
  const byNode = new Map();
  events.forEach(event => {
    const node = phase44NodeForEvent(event);
    let group = byNode.get(node);
    if (!group) { group = {node, events: []}; byNode.set(node, group); groups.push(group); }
    group.events.push(event);
  });
  let step = 0;
  return groups.map((group, groupIndex) => {
    const body = group.events.map(event => {
      step += 1;
      return event.role === 'query_programmer_tool' || event.role === 'senior_reviewer_tool' ? phase44ToolPanel(step, event) : event.role === 'query_programmer_model' ? phase44ModelPanel(step, event) : phase42CallPanel(step, event, `p44-${caseId}-${groupIndex}-${step}`);
    }).join('');
    return `<details class="node-group"><summary>Node ${groupIndex + 1}: ${esc(phase44NodeLabel(group.node))} · ${group.events.length} event${group.events.length === 1 ? '' : 's'}</summary><div class="node-group-body">${body}</div></details>`;
  }).join('');
}
async function showPhase44Run(i, button) {
  document.querySelectorAll('.run').forEach(x => x.classList.remove('active')); if (button) button.classList.add('active');
  const data = await (await fetch('/api/run?name=' + encodeURIComponent(visibleRuns[i].path || visibleRuns[i].name))).json();
  const rows = data.rows || []; const m = data.metrics || {};
  const productionSmoke = rows[0] && rows[0].mode === 'PRODUCTION_QUERY_PROGRAMMER_SUBGRAPH';
  const card = (label, value) => `<div class="card"><b>${esc(value ?? '—')}</b>${esc(label)}</div>`;
  const cards = [card('Cases', m.cases ?? rows.length), card(productionSmoke ? 'Completed' : 'Subgraph completed', productionSmoke ? m.completed : m.query_programmer_subgraph_completed), card(productionSmoke ? 'Model rounds' : 'Technically valid', productionSmoke ? m.model_rounds : m.technical_valid), card(productionSmoke ? 'Tool calls' : 'Tool rounds', productionSmoke ? m.tool_calls : m.tool_rounds), card(productionSmoke ? 'Validation calls' : 'Tool calls', productionSmoke ? m.validation_calls : m.tool_calls), card('Senior reviews', productionSmoke ? m.senior_reviews : m.senior_reviews)].join('');
  document.getElementById('content').innerHTML = `<h2>${esc(data.name)}</h2><div class="summary-note">${productionSmoke ? 'Production smoke: Functional Analyst → MCP catalog → Query Programmer subgraph → Senior Reviewer → MCP execution → synthesize.' : 'Phase 4.4: QueryTask → Query Programmer subgraph with model-initiated tools → external deterministic validation. The Functional Analyst is not invoked in this run.'} Each case shows the exact ordered LLM request, LLM response, application tool execution, tool result, and next LLM request with accumulated context. Events are grouped by LangGraph node; open a node to inspect its ordered calls.</div><details class="metrics-section" open><summary>Metrics</summary><div class="cards">${cards}</div></details>${rows.map((r, n) => { const finalStatus = r.final_status || 'UNRESOLVED'; const ok = productionSmoke ? finalStatus === 'completed' : finalStatus === 'QUERY_PROGRAMMER_COMPLETE'; const statusClass = ok ? 'ok' : finalStatus === 'insufficient_data' ? 'warn' : 'bad'; const marker = ok ? '✓' : finalStatus === 'insufficient_data' ? '!' : '✖'; const events = (r.audit_trail || []).filter(event => event.role !== 'query_programmer'); return `<details class="case" ${n===0?'open':''}><summary><b>${esc(r.id)}</b> · ${esc(r.question)} <span class="marker ${statusClass}">${marker} ${esc(finalStatus)}</span></summary><div class="case-body"><div class="case-status"><span class="badge ${r.technical_valid ? 'ok':'bad'}">Technical: ${r.technical_valid ? 'OK':'FAIL'}</span><span class="badge">Model rounds: ${esc(r.programmer_metadata && (r.programmer_metadata.model_rounds ?? r.programmer_metadata.agent_tool_rounds))}</span><span class="badge">Tool calls: ${esc(r.programmer_metadata && (r.programmer_metadata.tool_calls ?? r.programmer_metadata.internal_tool_calls))}</span></div><div class="flow">${phase44GroupedFlow(events, r.id)}</div><div class="grid">${panel('Functional requirement', r.query_task)}${panel('Query Programmer output', r.query_programmer_output)}${panel('MCP validation', r.validation)}${panel('Final response', r.response)}${panel('Final status', finalStatus)}${panel('Duration (ms)', r.duration_ms)}</div></div></details>`; }).join('') || '<p class="muted">No Phase 4.4 cases found.</p>'}`;
}
function phase42CallPanel(step, event, key=step) {
  const role = event.role || 'event';
  const internal = role === 'query_programmer_internal_iteration';
  const title = role === 'workflow_transition' ? `Workflow · ${event.stage || 'transition'}` : role === 'functional_analyst' || role === 'semantic_clarifier' ? 'Functional Analyst request' : role === 'functional_analyst_tool' ? `Functional Analyst tool · ${event.tool_name || event.tool || 'MCP'}` : role === 'functional_analyst_error' ? 'Functional Analyst LLM error' : role === 'sqlalchemy_query_developer' || role === 'query_programmer' ? 'Query Programmer LLM request' : role === 'senior_query_reviewer' ? 'Senior Query Reviewer LLM request' : role === 'hr_assistant_model' ? 'HR Assistant LLM request' : internal ? 'Query Programmer LLM internal iteration' : 'Application validation';
  const note = role === 'workflow_transition' ? `LangGraph transition · ${event.status || 'unknown status'}` : role === 'functional_analyst_tool' || role === 'senior_reviewer_tool' ? 'Executed by the application after an LLM tool call.' : role === 'functional_analyst_error' ? 'The LLM call failed before returning a response. The original request context and error are preserved below.' : role === 'query_validation' ? 'Generated by the application, not by the LLM' : internal ? `LLM call · internal Query Programmer iteration${event.prompt ? '' : ' · prompt metadata not persisted in this artifact'}` : `LLM call · ${role}`;
  const base = `phase42-${key}-${Math.random().toString(36).slice(2)}`;
  const metadata = {
    agent_id: event.agent_id,
    prompt_id: event.prompt_id,
    prompt_version: event.prompt_version,
    model: event.model,
    schema_version: event.schema_version,
    latency_ms: event.latency_ms,
  };
  const hasMetadata = Object.values(metadata).some(value => value !== null && value !== undefined);
  const open = step === 1 ? ' open' : '';
  const prompt = event.prompt || event.prompt_template;
  const messages = event.rendered_messages;
  const common = `${hasMetadata ? panel('Invocation metadata', metadata, '', JSON.stringify(metadata, null, 2), `${base}-metadata`, 'Copy metadata') : ''}${prompt ? panel('Prompt template', prompt, '', prompt, `${base}-prompt`, 'Copy prompt') : ''}${event.rendered_system_prompt ? panel('Rendered system prompt', event.rendered_system_prompt, '', event.rendered_system_prompt, `${base}-rendered-prompt`, 'Copy rendered prompt') : ''}${messages && (Array.isArray(messages) ? messages.length : true) ? panel('Rendered messages', messages, '', JSON.stringify(messages, null, 2), `${base}-messages`, 'Copy messages') : ''}`;
  if (role === 'workflow_transition') {
    return `<details class="call-step"${open}><summary>Step ${step}: ${esc(title)}</summary><div class="step-body"><div class="muted">${esc(note)}</div>${panel('Lifecycle', event.lifecycle || [event.status])}${panel('Status', event.status)}${panel('Snapshots', event.snapshots)}</div></details>`;
  }
  if (role === 'query_validation') {
    const output = event.output || {};
    const diagnostics = output.diagnostics || [];
    const details = diagnostics.map(item => ({stage: item.stage, code: item.code, exception_type: item.exception_type, message: item.message, line: item.line, offset: item.offset, text: item.text, source: item.source}));
    return `<details class="call-step"${open}><summary>Step ${step}: ${esc(title)}</summary><div class="step-body"><div class="muted">${esc(note)}</div>${panel('Input', event.input, '', JSON.stringify(event.input ?? null, null, 2), `${base}-input`, 'Copy input')}${panel('Output', output, '', JSON.stringify(output, null, 2), `${base}-output`, 'Copy output')}${details.length ? panel('Diagnostic details', details, '', JSON.stringify(details, null, 2), `${base}-diagnostics`, 'Copy diagnostic details') : ''}</div></details>`;
  }
  if (role === 'functional_analyst_tool') {
    return `<details class="call-step"${open}><summary>Step ${step}: ${esc(title)}</summary><div class="step-body"><div class="muted">${esc(note)}</div>${panel('Tool input', event.input, '', JSON.stringify(event.input ?? null, null, 2), `${base}-input`, 'Copy tool input')}${panel('Tool output', event.output, '', JSON.stringify(event.output ?? null, null, 2), `${base}-output`, 'Copy tool output')}</div></details>`;
  }
  if (role === 'senior_reviewer_tool') {
    return `<details class="call-step"${open}><summary>Step ${step}: ${esc(title)}</summary><div class="step-body"><div class="muted">${esc(note)}</div>${panel('Tool input', event.input, '', JSON.stringify(event.input ?? null, null, 2), `${base}-input`, 'Copy tool input')}${panel('Tool output', event.output, '', JSON.stringify(event.output ?? null, null, 2), `${base}-output`, 'Copy tool output')}</div></details>`;
  }
  if (role === 'functional_analyst_error') {
    return `<details class="call-step"${open}><summary>Step ${step}: ${esc(title)}</summary><div class="step-body"><div class="muted">${esc(note)}</div>${common}${panel('Error', event.error, '', JSON.stringify(event.error ?? null, null, 2), `${base}-error`, 'Copy error')}</div></details>`;
  }
  if (internal) return `<details class="call-step"${open}><summary>Step ${step}: ${esc(title)}</summary><div class="step-body"><div class="muted">${esc(note)}</div>${common}${panel('Internal input', event.input, '', JSON.stringify(event.input ?? null, null, 2), `${base}-input`, 'Copy internal input')}${panel('Internal output', event.output, '', JSON.stringify(event.output ?? null, null, 2), `${base}-output`, 'Copy internal output')}</div></details>`;
  return `<details class="call-step"${open}><summary>Step ${step}: ${esc(title)}</summary><div class="step-body"><div class="muted">${esc(note)}</div>${common}${panel('Input', event.input, '', JSON.stringify(event.input ?? null, null, 2), `${base}-input`, 'Copy input')}${panel('Response', event.output, '', JSON.stringify(event.output ?? null, null, 2), `${base}-response`, 'Copy response')}</div></details>`;
}
function phase42MetricCards(metrics, mode, rows) {
  const card = (label, value) => `<div class="card"><b>${esc(value ?? '—')}</b>${esc(label)}</div>`;
  const cardsFor = (m) => {
    const queryGeneration = m.query_generation || {};
    const firstPass = m.first_pass_technical_validity || {};
    const technicalRepair = m.technical_repair || {};
    const senior = m.senior_review || {};
    const semanticRepair = m.semantic_repair || {};
    const final = m.final || {};
    return [
      card('Cases', m.cases ?? rows.length),
      card('Executions', m.executions ?? m.cases ?? rows.length),
      card('Queries generated', queryGeneration.count),
      card('First-pass technically valid', firstPass.count),
      card('Technical valid final', final.technical_valid),
      card('Senior reviews', senior.reviewed_cases),
      card('Final approved', final.semantic_approved),
      card('Revision requested', senior.revision_requested_cases),
      card('Repair success', (technicalRepair.successful_cases || 0) + (semanticRepair.successful_cases || 0)),
      card('Needs clarification', final.needs_clarification),
      card('Max revisions', final.max_semantic_revisions_reached),
    ].join('');
  };
  const modes = [...new Set(rows.map(row => row.mode).filter(Boolean))];
  if (modes.length > 1) {
    const content = modes.map(currentMode => {
      const key = currentMode === 'QUERY_DEVELOPER_ONLY' ? 'query_developer_only' : 'agent_team';
      const label = currentMode === 'QUERY_DEVELOPER_ONLY' ? 'Query Developer only' : 'Agent team';
      return `<h3>${label}</h3><div class="cards">${cardsFor(metrics[key] || {})}</div>`;
    }).join('');
    return `<details class="metrics-section" open><summary>Execution metrics</summary>${content}</details>`;
  }
  const key = mode === 'QUERY_DEVELOPER_ONLY' ? 'query_developer_only' : 'agent_team';
  return `<details class="metrics-section" open><summary>Execution metrics</summary><div class="cards">${cardsFor(metrics[key] || metrics || {})}</div></details>`;
}
async function showPhase42Run(i, button) {
  document.querySelectorAll('.run').forEach(x => x.classList.remove('active')); if (button) button.classList.add('active');
  const data = await (await fetch('/api/run?name=' + encodeURIComponent(visibleRuns[i].path || visibleRuns[i].name))).json();
  const rows = data.rows || [];
  const approved = rows.filter(r => r.final_status === 'APPROVED').length;
  const technical = rows.filter(r => r.technical_valid).length;
  document.getElementById('content').innerHTML = `<h2>${esc(data.name)}</h2><div class="summary-note">Each case is displayed as an ordered execution flow. “Application validation” is deterministic and is not an LLM call.</div>${phase42MetricCards(data.metrics, rows[0] && rows[0].mode, rows)}${rows.map((r, n) => { const finalStatus = r.final_status || 'UNRESOLVED'; const analystOnly = r.mode === 'FUNCTIONAL_ANALYST_ONLY'; const flowComplete = finalStatus === 'APPROVED' || finalStatus === 'QUERY_DEVELOPER_ONLY_COMPLETE' || finalStatus === 'FUNCTIONAL_ANALYST_COMPLETE'; const ok = analystOnly ? finalStatus === 'FUNCTIONAL_ANALYST_COMPLETE' || finalStatus === 'NEEDS_CLARIFICATION' : flowComplete && (finalStatus === 'APPROVED' || r.technical_valid); const statusClass = ok ? 'ok' : 'bad'; return `<details class="case" ${n===0?'open':''}><summary><b>${esc(r.id)}</b> · ${esc(r.mode)} · ${esc(r.question)} <span class="marker ${statusClass}">${ok ? '✓' : '✖'} ${esc(finalStatus)}</span></summary><div class="case-body">${analystOnly ? '' : `<div class="case-status"><span class="badge ${r.technical_valid ? 'ok':'bad'}">Technical: ${r.technical_valid ? 'OK':'FAIL'}</span><span class="badge">Revision count: ${esc(r.revision_count)}</span></div>`}<div class="flow">${(r.audit_trail || []).map((event, index) => phase42CallPanel(index + 1, event)).join('')}</div><div class="grid">${panel('Final status', finalStatus)}${panel('Duration (ms)', r.duration_ms)}</div></div></details>`; }).join('') || '<p class="muted">No Phase 4.2 cases found.</p>'}`;
}
async function showRun(i, button) {
  if (visibleRuns[i] && visibleRuns[i].name.startsWith('semantic-prompt-playground-tests-')) { showPromptRun(i, button); return; }
  if (visibleRuns[i] && visibleRuns[i].phase === 'phase44') { showPhase44Run(i, button); return; }
  if (visibleRuns[i] && (visibleRuns[i].phase === 'phase42' || visibleRuns[i].name.startsWith('direct-sqlalchemy-phase42-'))) { showPhase42Run(i, button); return; }
  if (visibleRuns[i] && visibleRuns[i].name.startsWith('semantic-clarifier-')) { showClarifierRun(i, button); return; }
  document.querySelectorAll('.run').forEach(x => x.classList.remove('active')); if (button) button.classList.add('active');
  const data = await (await fetch('/api/run?name=' + encodeURIComponent(visibleRuns[i].path || visibleRuns[i].name))).json();
  const m = data.metrics || {}; const rows = data.rows || [];
  const count = (fn) => rows.filter(fn).length;
  const summary = [
    ['Ejecuciones', rows.length],
    ['Respuesta estructurada', count(r => r.response) + '/' + rows.length],
    ['Oracle aceptado', count(r => r.outcome_acceptable) + '/' + rows.length],
    ['Validación de sintaxis', count(r => !(r.validation_errors || []).length) + '/' + rows.length],
    ['Statement construido', count(r => r.statement_built) + '/' + rows.length],
    ['PostgreSQL compilado', count(r => r.compiled_sql) + '/' + rows.length],
    ['OK completamente', count(r => r.outcome_acceptable && !(r.validation_errors || []).length && r.statement_built && r.compiled_sql) + '/' + rows.length]
  ].map(([k,v]) => `<div class="card"><b>${esc(v)}</b>${esc(k)}</div>`).join('');
  document.getElementById('content').innerHTML = `<h2>${esc(data.name)}</h2><div class="summary-note"><b>Cómo leer estos estados:</b> “Oracle aceptado” indica que la respuesta coincide con la expectativa registrada del caso. No significa necesariamente que el query sea válido. “Validación de sintaxis”, “Statement construido” y “PostgreSQL compilado” muestran si el query realmente pasó las etapas técnicas.</div><div class="cards">${summary}</div>${rows.map((r, n) => {
    const p = r.viewer_prompts || {}; const response = r.response || {}; const clarification = r.clarification || null;
    const suffix = `${esc(r.id)}-${esc(r.repetition)}-${n}`;
    const promptNote = (persisted) => persisted ? 'persisted literal prompt' : 'reconstructed from current code';
    const validSyntax = !(r.validation_errors || []).length;
    const badge = (label, ok) => `<span class="badge ${ok ? 'ok':'bad'}">${esc(label)}: ${ok ? 'OK':'FAIL'}</span>`;
    const fullyOk = Boolean(r.outcome_acceptable && validSyntax && r.statement_built && r.compiled_sql);
    const generatorReplays = (r.manual_replays || []).filter(x => x.role === 'generator');
    const latestReplay = generatorReplays.length ? generatorReplays[generatorReplays.length - 1] : null;
    const replayPassed = Boolean(latestReplay && latestReplay.full_validation_passed);
    const displayOracle = latestReplay ? Boolean(latestReplay.oracle_acceptable) : r.outcome_acceptable;
    const displaySyntax = latestReplay ? !(latestReplay.validation_errors || []).length : validSyntax;
    const errorCode = fullyOk ? 'OK' : !r.outcome_acceptable ? 'ORACLE_FAIL' : (r.validation_errors || []).map(e => e.split(':')[0]).includes('PYTHON_SYNTAX') ? 'ERROR_SINTAXIS' : (r.validation_errors || []).map(e => e.split(':')[0]).includes('UNKNOWN_NAME') ? 'ERROR_NOMBRE' : (r.validation_errors || []).map(e => e.split(':')[0]).includes('BUILD_ERROR') ? 'ERROR_CONSTRUCCION' : (r.validation_errors || []).length ? 'ERROR_VALIDACION' : !r.statement_built ? 'ERROR_CONSTRUCCION' : 'ERROR_COMPILACION';
    const marker = replayPassed
      ? `<span class="marker ok">✓ REPLAY_OK</span>`
      : `<span class="marker ${fullyOk ? 'ok':'bad'}">${fullyOk ? '✓':'✖'} ${errorCode}</span>`;
    const questionCopyId = `copy-question-${suffix}`;
    const clarificationCopyId = `copy-clarification-${suffix}`;
    const responseCopyId = `copy-response-${suffix}`;
    const syntaxCopyId = `copy-syntax-${suffix}`;
    const responseJson = JSON.stringify(response, null, 2);
    const syntax = response.sqlalchemy ? response.sqlalchemy.replace(/\s*\n\s*/g, ' ').trim() : '';
    return `<details class="case" ${n===0?'open':''}><summary><b>${esc(r.id)}</b> · rep ${esc(r.repetition)} · ${esc(r.question)} ${marker}</summary><div class="case-body"><div class="case-status">${badge('Oracle', displayOracle)}${badge('Sintaxis', displaySyntax)}${badge('Construcción', latestReplay ? latestReplay.statement_built : r.statement_built)}${badge('Compilación', latestReplay ? Boolean(latestReplay.compiled_sql) : Boolean(r.compiled_sql))}${latestReplay ? badge('Replay', replayPassed) : ''}</div><div class="grid">${panel('Question', r.question, '', r.question, questionCopyId, 'Copy question')}${panel('Clarifier response', clarification, '', JSON.stringify(clarification, null, 2), clarificationCopyId, 'Copy response')}${panel('Generator response', response, '', responseJson, responseCopyId, 'Copy response', syntax, syntaxCopyId, 'Copy syntax')}${panel('Compiled SQL / result', r.compiled_sql)}${panel('Validation errors', r.validation_errors)}${latestReplay ? panel('Latest generator replay', latestReplay) : ''}${panel('Duration (ms)', r.duration_ms)}</div><div class="editor"><h3>Replay clarifier</h3><div class="muted">${promptNote(p.clarifier_persisted)}</div><textarea id="clarifier-${suffix}">${esc(p.clarifier)}</textarea><button onclick="copyPrompt('clarifier-${suffix}', this)">Copy clarifier prompt</button><button onclick="replay('${esc(data.name)}','${esc(r.id)}',${Number(r.repetition)},'clarifier','clarifier-${suffix}')">Send clarifier prompt</button><h3>Replay generator</h3><div class="muted">${promptNote(p.generator_persisted)}</div><textarea id="generator-${suffix}">${esc(p.generator)}</textarea><button onclick="copyPrompt('generator-${suffix}', this)">Copy generator prompt</button><button onclick="replay('${esc(data.name)}','${esc(r.id)}',${Number(r.repetition)},'generator','generator-${suffix}')">Send generator prompt</button><div id="replay-${suffix}"></div></div></div></details>`;
  }).join('')}`;
}
async function replay(run, caseId, repetition, role, textareaId) {
  const target = document.getElementById('replay-' + textareaId.split('-').slice(1).join('-'));
  if (target) target.textContent = 'Sending...';
  const prompt = document.getElementById(textareaId).value;
  const response = await fetch('/api/replay', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({run, case_id:caseId, repetition, role, prompt})});
  const data = await response.json().catch(() => ({error: response.statusText}));
  if (target) target.innerHTML = response.ok ? panel('Manual replay result', data.replay) : `<span class="bad">${esc(data.error || 'Replay failed')}</span>`;
  if (response.ok) {
    await loadRuns();
    const index = visibleRuns.findIndex(x => x.name === run);
    if (index >= 0) showRun(index);
  }
}
async function copyPrompt(textareaId, button) {
  const text = document.getElementById(textareaId).value;
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    const textarea = document.getElementById(textareaId);
    textarea.focus();
    textarea.select();
    document.execCommand('copy');
  }
  const original = button.textContent;
  button.textContent = 'Copied';
  setTimeout(() => { button.textContent = original; }, 1200);
}
async function copyHidden(sourceId, button) {
  const text = document.getElementById(sourceId).value;
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    const source = document.getElementById(sourceId);
    source.select();
    document.execCommand('copy');
  }
  const original = button.textContent;
  button.textContent = 'Copied';
  setTimeout(() => { button.textContent = original; }, 1200);
}
loadRuns();
</script>
</body></html>"""


class ViewerHandler(BaseHTTPRequestHandler):
    def _send(self, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error_json(self, status: int, message: str) -> None:
        body = json.dumps({"ok": False, "error": message}, ensure_ascii=False)
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(HTML, "text/html; charset=utf-8")
            return
        if parsed.path == "/api/runs":
            payload = [_run_summary(path) for path in _run_dirs()]
            self._send(json.dumps(payload), "application/json")
            return
        if parsed.path == "/api/phases":
            self._send(
                json.dumps(
                    [
                        {"name": path.name, "runs": len(_run_dirs(path.name))}
                        for path in _phase_dirs()
                    ]
                ),
                "application/json",
            )
            return
        if parsed.path == "/api/prompt":
            prompt_format = parse_qs(parsed.query).get("format", ["generation"])[0]
            if prompt_format == "generation":
                try:
                    _ensure_project_imports()
                    sys.path.insert(0, str(SPIKES_DIR))
                    import direct_sqlalchemy_phase412 as phase412

                    prompt = phase412.GENERATOR_PROMPT
                except ImportError as error:
                    self._send_error_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        f"Generator prompt is unavailable: {error}",
                    )
                    return
            else:
                prompt_path = PROMPT_FILES.get(prompt_format)
                if prompt_path is None or not prompt_path.is_file():
                    self._send_error_json(HTTPStatus.NOT_FOUND, "prompt file not found")
                    return
                prompt = prompt_path.read_text(encoding="utf-8")
            self._send(
                json.dumps(
                    {"format": prompt_format, "prompt": prompt},
                    ensure_ascii=False,
                ),
                "application/json",
            )
            return
        if parsed.path == "/api/prompt-tests":
            tests = []
            for directory in _prompt_test_dirs():
                for path in sorted(directory.glob("*.json"), reverse=True):
                    try:
                        payload = _read_json(path)
                    except (OSError, json.JSONDecodeError):
                        continue
                    tests.append(
                        {
                            "name": path.name,
                            "path": path.relative_to(RUNS_DIR).as_posix(),
                            "folder": directory.name,
                            "created_at": payload.get(
                                "timestamp",
                                datetime.fromtimestamp(
                                    path.stat().st_mtime, tz=timezone.utc
                                ).isoformat(),
                            ),
                            "output_format": payload.get("output_format", "unknown"),
                        }
                    )
            self._send(json.dumps(tests, ensure_ascii=False), "application/json")
            return
        if parsed.path == "/api/prompt-test":
            name = parse_qs(parsed.query).get("path", [""])[0]
            candidate = (RUNS_DIR / name).resolve()
            allowed_dirs = {directory.resolve() for directory in _prompt_test_dirs()}
            if candidate.parent not in allowed_dirs or candidate.suffix != ".json":
                self._send_error_json(HTTPStatus.NOT_FOUND, "prompt test not found")
                return
            try:
                payload = _read_json(candidate)
            except (OSError, json.JSONDecodeError):
                self._send_error_json(HTTPStatus.NOT_FOUND, "prompt test not found")
                return
            payload["name"] = candidate.name
            self._send(json.dumps(payload, ensure_ascii=False), "application/json")
            return
        if parsed.path == "/api/run":
            name = parse_qs(parsed.query).get("name", [""])[0]
            candidate = (RUNS_DIR / name).resolve()
            try:
                candidate.relative_to(RUNS_DIR.resolve())
            except ValueError:
                candidate = None
            if candidate is None or not candidate.is_dir():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._send(json.dumps(_run_payload(candidate), ensure_ascii=False), "application/json")
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/replay":
            self._handle_replay()
            return
        if path == "/api/test-prompt":
            self._handle_test_prompt()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        if urlparse(self.path).path != "/api/run":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            relative_name = str(payload.get("path", ""))
            candidate = _safe_run_directory(relative_name)
            if candidate is None:
                self._send_error_json(HTTPStatus.NOT_FOUND, "test run not found")
                return
            shutil.rmtree(candidate)
            self._send_json({"ok": True, "deleted": relative_name})
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"could not delete test run: {error}")

    def _send_json(self, payload: dict[str, object]) -> None:
        self._send(json.dumps(payload, ensure_ascii=False), "application/json")

    def _handle_replay(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            run_name = str(payload["run"])
            role = str(payload["role"])
            case_id = str(payload["case_id"])
            repetition = int(payload["repetition"])
            prompt = str(payload["prompt"])
            if role not in {"clarifier", "generator"} or not prompt.strip():
                raise ValueError("role must be clarifier/generator and prompt is required")
            candidate = (RUNS_DIR / run_name).resolve()
            try:
                candidate.relative_to(RUNS_DIR.resolve())
            except ValueError:
                candidate = None
            if candidate is None or not candidate.is_dir():
                raise FileNotFoundError(run_name)
            _load_dotenv()
            _ensure_project_imports()
            from openai import OpenAI
            from peopleops_api.analysis_workflow import (
                _openai_strict_schema,
                _response_output_text,
            )

            sys.path.insert(0, str(SPIKES_DIR))
            import direct_sqlalchemy_phase41 as phase41
            import direct_sqlalchemy_phase412 as phase412

            output_model = (
                phase412.ClarificationResponse
                if role == "clarifier"
                else phase41.SQLAlchemyGenerationResponse
            )
            source_rows = _read_run_rows(candidate)
            source_row = next(
                (
                    row
                    for row in source_rows
                    if row.get("id") == case_id
                    and row.get("repetition") == repetition
                ),
                None,
            )
            if source_row is None:
                raise KeyError(f"Case not found: {case_id}/{repetition}")
            if role == "generator":
                replay_input = source_row.get("generator_input")
                if replay_input is None and source_row.get("clarification"):
                    clarification = phase412.ClarificationResponse.model_validate(
                        source_row["clarification"]
                    )
                    replay_input = phase412.generator_input(clarification)
                if replay_input is None:
                    raise ValueError("generator input is unavailable for this case")
            else:
                replay_input = source_row.get("question")
                if not replay_input:
                    raise ValueError("clarifier input is unavailable for this case")
            client = OpenAI(
                api_key=os.environ["OPENAI_API_KEY"], timeout=30.0, max_retries=0
            )
            response = client.responses.create(
                model="gpt-4o-mini",
                instructions=prompt,
                input=[
                    {
                        "role": "user",
                        "content": (
                            json.dumps(replay_input, ensure_ascii=False)
                            if isinstance(replay_input, dict)
                            else str(replay_input)
                        ),
                    }
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": output_model.__name__,
                        "strict": True,
                        "schema": _openai_strict_schema(
                            output_model.model_json_schema()
                        ),
                    }
                },
                max_output_tokens=4096,
            )
            result = output_model.model_validate_json(
                _response_output_text(response)
            )
            replay = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "role": role,
                "prompt": prompt,
                "instructions": prompt,
                "input": replay_input,
                "response": result.model_dump(mode="json"),
            }
            if role == "generator":
                syntax_errors = phase41.validate_python_expression(result.sqlalchemy or "")
                if syntax_errors:
                    statement, errors, compiled_sql = None, syntax_errors, None
                else:
                    statement, errors = phase41.build_statement(result.sqlalchemy or "")
                    if statement is not None and not errors:
                        compiled_sql, compile_errors = phase41.compile_postgresql(statement)
                        errors.extend(compile_errors)
                    else:
                        compiled_sql = None
                replay.update({
                    "validation_errors": errors,
                    "statement_built": statement is not None,
                    "compiled_sql": compiled_sql,
                })
                case = _phase412_case(case_id)
                if case is not None:
                    oracle_acceptable = result.status in case["accepted_outcomes"]
                    if (
                        result.status == "QUERY"
                        and case.get("query_requires_declared_assumption")
                        and not result.assumptions
                    ):
                        oracle_acceptable = False
                    technical_acceptable = (
                        result.status == "NEEDS_INFO"
                        or (
                            result.status == "QUERY"
                            and not errors
                            and statement is not None
                            and compiled_sql is not None
                        )
                    )
                    replay.update({
                        "oracle_acceptable": oracle_acceptable,
                        "technical_acceptable": technical_acceptable,
                        "full_validation_passed": (
                            oracle_acceptable and technical_acceptable
                        ),
                        "validation_scope": "phase412_case_expectations",
                    })
                else:
                    replay.update({
                        "validation_scope": "technical_only",
                        "full_validation_passed": (
                            result.status == "NEEDS_INFO"
                            or (
                                not errors
                                and statement is not None
                                and compiled_sql is not None
                            )
                        ),
                    })
            _persist_manual_replay(candidate, case_id, repetition, replay)
            self._send(json.dumps({"ok": True, "replay": replay}, ensure_ascii=False), "application/json")
        except ImportError as error:
            self._send_error_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                f"Project dependencies are unavailable. Start the viewer with Poetry: {error}",
            )
        except (KeyError, TypeError, ValueError, FileNotFoundError, OSError) as error:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(error))

    def _handle_test_prompt(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            model = str(payload.get("model") or "gpt-4o-mini")
            purpose = str(payload.get("purpose") or "semantic-prompt-playground")
            instructions = str(payload.get("instructions") or "")
            user_input = str(payload.get("user_input") or "")
            output_format = str(payload.get("output_format") or "generation")
            if not instructions.strip():
                raise ValueError("instructions are required")
            if output_format not in {"clarification", "generation"}:
                raise ValueError("unsupported output format")
            _load_dotenv()
            _ensure_project_imports()
            from openai import OpenAI
            from peopleops_api.analysis_workflow import (
                _openai_strict_schema,
                _response_output_text,
            )

            sys.path.insert(0, str(SPIKES_DIR))
            import direct_sqlalchemy_phase41 as phase41
            import direct_sqlalchemy_phase412 as phase412

            input_format = str(payload.get("input_format") or "text")
            if input_format not in {"none", "text", "json"}:
                raise ValueError("unsupported input format")
            output_model = (
                phase412.ClarificationResponse
                if output_format == "clarification"
                else phase41.SQLAlchemyGenerationResponse
            )
            if input_format == "none":
                # Responses API rejects both a missing and an empty input. This
                # neutral marker keeps user input optional without inventing a
                # user request or exposing an empty JSON value to the model.
                api_input = "[No additional user input provided.]"
                input_request = None
            elif input_format == "json":
                try:
                    user_input_value = json.loads(user_input)
                except json.JSONDecodeError as error:
                    raise ValueError(f"User input is not valid JSON: {error.msg}") from error
                api_input = json.dumps(user_input_value, ensure_ascii=False)
                input_request = (
                    user_input_value
                    if isinstance(user_input_value, dict)
                    else {"value": user_input_value}
                )
            else:
                api_input = user_input
                input_request = {"user_request": api_input}
            if api_input is not None and not api_input.strip():
                raise ValueError("user input is required")
            started = datetime.now(timezone.utc)
            client = OpenAI(
                api_key=os.environ["OPENAI_API_KEY"], timeout=30.0, max_retries=0
            )
            request = {
                "model": model,
                "instructions": instructions,
                "input": api_input,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": output_model.__name__,
                        "strict": True,
                        "schema": _openai_strict_schema(
                            output_model.model_json_schema()
                        ),
                    }
                },
                "max_output_tokens": 4096,
            }
            if input_format != "none":
                request["input"] = [{"role": "user", "content": api_input}]
            response = client.responses.create(**request)
            result = output_model.model_validate_json(_response_output_text(response))
            result_json = result.model_dump(mode="json")
            if output_format == "generation" and input_request is not None:
                result_json["input_request"] = input_request
            record = {
                "timestamp": started.isoformat(),
                "purpose": purpose,
                "model": model,
                "output_format": output_format,
                "instructions": instructions,
                "input_format": input_format,
                "input": api_input,
                "response": result_json,
            }
            saved_artifact = _persist_playground_result(record)
            self._send(json.dumps({
                "response": result_json,
                "metadata": {
                    "model": model,
                    "purpose": purpose,
                    "output_format": output_format,
                    "input_format": input_format,
                },
                "saved_artifact": saved_artifact,
            }, ensure_ascii=False), "application/json")
        except ImportError as error:
            self._send_error_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                f"Project dependencies are unavailable. Start the viewer with Poetry: {error}",
            )
        except (KeyError, TypeError, ValueError, OSError) as error:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(error))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ViewerHandler)
    print(f"Viewer available at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
