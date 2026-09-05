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
    return sorted(
        (
            path
            for path in RUNS_DIR.glob(f"{PROMPT_TESTS_PREFIX}*")
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
    directory = RUNS_DIR / f"{prefix}1"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _sync_prompt_tests_raw(directory: Path) -> None:
    """Consolidate one prompt-test folder into its local JSONL index."""
    if not directory.is_dir():
        return

    rows: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        row = dict(payload)
        row["artifact"] = path.name
        rows.append(row)

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


def _run_dirs() -> list[Path]:
    return sorted(
        (path for path in RUNS_DIR.iterdir() if path.is_dir()),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )


def _run_summary(path: Path) -> dict:
    raw_path = path / "raw_responses.jsonl"
    return {
        "name": path.name,
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


def _run_payload(run_dir: Path) -> dict:
    manifest_path = run_dir / "manifest.json"
    raw_path = run_dir / "raw_responses.jsonl"
    metrics_path = run_dir / "metrics.json"
    rows = _read_jsonl(raw_path) if raw_path.exists() else []
    for row in rows:
        reconstructed = _reconstructed_prompts(row)
        row["viewer_prompts"] = {
            "clarifier": row.get("clarifier_prompt") or reconstructed["clarifier"],
            "generator": row.get("generator_prompt") or reconstructed["generator"],
            "clarifier_persisted": "clarifier_prompt" in row,
            "generator_persisted": "generator_prompt" in row,
        }
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
            row.setdefault("manual_replays", []).append(replay)
            break
    else:
        raise KeyError(f"Case not found: {case_id}/{repetition}")
    content = "\n".join(
        json.dumps(row, ensure_ascii=False, default=str) for row in rows
    ) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=run_dir, delete=False
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, raw_path)


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
aside { padding: 16px; border-right: 1px solid #374151; overflow: auto; }
section { padding: 18px 24px; overflow: auto; }
button, select, input { background: #1f2937; color: #e5e7eb; border: 1px solid #4b5563; border-radius: 6px; padding: 8px; }
button { cursor: pointer; width: auto; }
.run { display: block; width: 100%; text-align: left; margin: 6px 0; }
.run.active { border-color: #60a5fa; background: #1e3a5f; }
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.cards { display: flex; gap: 10px; flex-wrap: wrap; margin: 14px 0; }
.card { background: #1f2937; border: 1px solid #374151; border-radius: 8px; padding: 10px 14px; min-width: 120px; }
.card b { display: block; font-size: 18px; color: #93c5fd; }
.summary-note { padding: 12px; background: #3b2f12; border: 1px solid #92701c; border-radius: 8px; margin: 12px 0; }
.case-status { display: flex; gap: 6px; flex-wrap: wrap; padding: 10px 0; }
.badge { border-radius: 12px; padding: 3px 8px; font-size: 12px; border: 1px solid #4b5563; }
.badge.ok { background: #12351f; } .badge.bad { background: #431b1b; }
.marker { margin-left: 8px; font-weight: 700; }
.marker.ok { color: #86efac; } .marker.bad { color: #fca5a5; }
.case { border: 1px solid #374151; border-radius: 8px; margin: 10px 0; overflow: hidden; }
.case > summary { cursor: pointer; padding: 12px; background: #1f2937; }
.case-body { padding: 14px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.flow { display: flex; flex-direction: column; gap: 14px; margin: 12px 0; }
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
<main><aside><button onclick="loadRuns()">Refresh runs</button><button onclick="showPlayground()">Open generator tester</button><label class="filter">Show <select id="run-filter" onchange="renderRuns()"><option value="phase412">Phase 4.1.2</option><option value="phase42">Phase 4.2</option><option value="clarifier-tests">Clarifier tests</option><option value="prompt-tests">Prompt tester</option><option value="all">All experiments</option></select></label><div id="runs"></div></aside><section id="content"><p>Select a run.</p></section></main>
<script>
let runs = [];
let visibleRuns = [];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = x => {
  if (typeof x !== 'string') return JSON.stringify(x ?? null, null, 2);
  try { return JSON.stringify(JSON.parse(x), null, 2); } catch (error) { return x; }
};
function panel(title, value, note='', copyText=null, copyId='', copyLabel='', extraCopyText=null, extraCopyId='', extraCopyLabel='') { const copy = copyText === null ? '' : `<textarea class="copy-source" id="${esc(copyId)}">${esc(copyText)}</textarea><button type="button" onclick="copyHidden('${esc(copyId)}', this)">${esc(copyLabel || `Copy ${title.toLowerCase()}`)}</button>`; const extraCopy = extraCopyText === null ? '' : `<textarea class="copy-source" id="${esc(extraCopyId)}">${esc(extraCopyText)}</textarea><button type="button" onclick="copyHidden('${esc(extraCopyId)}', this)">${esc(extraCopyLabel)}</button>`; return `<div class="panel"><h4>${esc(title)} ${note ? `<span class="muted">(${esc(note)})</span>` : ''}</h4><pre>${esc(pretty(value))}</pre>${copy}${extraCopy}</div>`; }
async function loadRuns() {
  runs = await (await fetch('/api/runs')).json();
  renderRuns();
}
function showPlayground() {
  document.getElementById('content').innerHTML = `<h2>Generator prompt tester</h2><div class="summary-note">This sends one independent structured request to the generator. The clarifier is shown only in stored run details; this tester defaults to SQLAlchemyGenerationResponse. Instructions and user input are sent through separate API fields. Each test is saved as its own JSON file in a daily folder named <code>evaluation/runs/semantic-prompt-playground-tests-YYYYMMDD-N/</code>. Use the “Prompt tester” filter to inspect those folders.</div><div class="playground"><label>Model<input id="test-model" value="gpt-4o-mini"></label><label>Purpose (optional)<input id="test-purpose" value="semantic-prompt-playground"></label><label>Output format<select id="test-format" onchange="loadDefaultInstructions()"><option value="generation" selected>SQLAlchemyGenerationResponse (generator)</option><option value="clarification">ClarificationResponse (clarifier)</option></select></label><label>Instructions<textarea id="test-instructions" placeholder="Rules and context for the generator"></textarea><button type="button" onclick="copyTextarea('test-instructions', this)">Copy instructions</button></label><label>User input format<select id="test-input-format" onchange="toggleUserInput()"><option value="none">None</option><option value="json" selected>JSON</option><option value="text">Text</option></select></label><label>User input (optional)<textarea id="test-input" placeholder="Enter the clarifier JSON or the user's request"></textarea><button type="button" onclick="copyTextarea('test-input', this)">Copy user input</button></label><button onclick="sendTestPrompt()">Send generator prompt</button><div id="test-result"></div></div>`;
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
  visibleRuns = filter === 'phase412' ? runs.filter(r => r.name.startsWith('direct-sqlalchemy-phase412-')) : filter === 'phase42' ? runs.filter(r => r.name.startsWith('direct-sqlalchemy-phase42-')) : filter === 'clarifier-tests' ? runs.filter(r => r.name.startsWith('semantic-clarifier-')) : filter === 'prompt-tests' ? runs.filter(r => r.name.startsWith('semantic-prompt-playground-tests-')) : runs;
  document.getElementById('runs').innerHTML = visibleRuns.map((r, i) => `<button class="run ${i===0?'active':''}" onclick="showRun(${i}, this)"><b>${esc(r.name)}</b><br><span class="muted">${r.rows} filas · creado ${new Date(r.created_at).toLocaleString()}</span></button>`).join('') || '<p class="muted">No hay runs para este filtro.</p>';
  if (visibleRuns.length) {
    const first = document.querySelector('.run');
    if (visibleRuns[0].name.startsWith('semantic-prompt-playground-tests-')) showPromptRun(0, first);
    else if (visibleRuns[0].name.startsWith('semantic-clarifier-')) showClarifierRun(0, first);
    else showRun(0, first);
  }
}
async function showPromptRun(i, button) {
  document.querySelectorAll('.run').forEach(x => x.classList.remove('active')); if (button) button.classList.add('active');
  const data = await (await fetch('/api/run?name=' + encodeURIComponent(visibleRuns[i].name))).json();
  const rows = data.rows || [];
  document.getElementById('content').innerHTML = `<h2>${esc(data.name)}</h2><div class="summary-note">Prompt tester artifacts from this folder. Each row is one independent API call and preserves its complete instructions, input, and response.</div><div class="cards"><div class="card"><b>${rows.length}</b>Tests</div><div class="card"><b>${esc(data.name.slice(-2))}</b>Folder</div></div>${rows.map((r, n) => { const artifact = r.artifact || ''; const output = r.output_format || 'unknown'; const stamp = r.timestamp ? new Date(r.timestamp).toLocaleString() : 'unknown date'; let request = r.input || ''; try { const parsed = JSON.parse(request); if (parsed && typeof parsed === 'object') request = parsed.original_user_request || parsed.clarified_request_english || request; } catch (error) {} const status = r.response && r.response.status ? ` · ${r.response.status}` : ''; return `<button class="run" onclick="showPromptTest('${esc(data.name + '/' + artifact)}')"><b>${esc(request)}</b>${esc(status)}<br><span class="muted">${esc(stamp)} · ${esc(output)} · ${esc(artifact)}</span></button>`; }).join('') || '<p class="muted">No prompt tests found.</p>'}`;
}
function phase42Timeline(events) {
  if (!events || !events.length) return '<p class="muted">No call audit available.</p>';
  return `<div class="timeline">${events.map((event, index) => `<div class="panel"><h4>${index + 1}. ${esc(event.role || 'event')}</h4><pre>${esc(JSON.stringify({prompt: event.prompt, input: event.input, output: event.output, latency_ms: event.latency_ms}, null, 2))}</pre></div>`).join('')}</div>`;
}
async function showClarifierRun(i, button) {
  document.querySelectorAll('.run').forEach(x => x.classList.remove('active')); if (button) button.classList.add('active');
  const data = await (await fetch('/api/run?name=' + encodeURIComponent(visibleRuns[i].name))).json();
  const rows = data.rows || [];
  const needs = rows.filter(r => r.response && r.response.needs_clarification).length;
  document.getElementById('content').innerHTML = `<h2>${esc(data.name)}</h2><div class="summary-note">Functional Analyst / Semantic Clarifier tests. These calls do not generate or validate SQLAlchemy queries.</div><div class="cards"><div class="card"><b>${rows.length}</b>Cases</div><div class="card"><b>${needs}/${rows.length}</b>Needs clarification</div><div class="card"><b>${esc(data.manifest && data.manifest.prompt_version || '')}</b>Prompt version</div></div>${rows.map((r, n) => { const response = r.response || {}; const needsClarification = Boolean(response.needs_clarification); const statusClass = needsClarification ? 'bad' : 'ok'; const suffix = `clarifier-${esc(r.id)}-${n}`; return `<details class="case" ${n===0?'open':''}><summary><b>${esc(r.id)}</b> · ${esc(r.question)} <span class="marker ${statusClass}">${needsClarification ? '!' : '✓'} ${needsClarification ? 'NEEDS_CLARIFICATION' : 'CLARIFIED'}</span></summary><div class="case-body"><div class="case-status"><span class="badge ${needsClarification ? 'bad':'ok'}">Needs clarification: ${needsClarification ? 'YES':'NO'}</span><span class="badge">Latency: ${esc(r.latency_ms)} ms</span></div><div class="grid">${panel('Question', r.question, '', r.question, `${suffix}-question`, 'Copy question')}${panel('Prompt', r.prompt, '', r.prompt, `${suffix}-prompt`, 'Copy prompt')}${panel('Input', r.input, '', JSON.stringify(r.input, null, 2), `${suffix}-input`, 'Copy input')}${panel('Response', response, '', JSON.stringify(response, null, 2), `${suffix}-response`, 'Copy response')}${panel('Metadata', r.metadata)}</div></div></details>`; }).join('') || '<p class="muted">No clarifier tests found.</p>'}`;
}
async function showPhase42RunLegacy(i, button) {
  document.querySelectorAll('.run').forEach(x => x.classList.remove('active')); if (button) button.classList.add('active');
  const data = await (await fetch('/api/run?name=' + encodeURIComponent(visibleRuns[i].name))).json();
  const rows = data.rows || []; const m = data.metrics || {};
  const mode = rows[0] && rows[0].mode ? rows[0].mode : 'mixed';
  const approved = rows.filter(r => r.final_status === 'APPROVED').length;
  const technical = rows.filter(r => r.technical_valid).length;
  document.getElementById('content').innerHTML = `<h2>${esc(data.name)}</h2><div class="summary-note">Phase 4.2 audit. Technical validity and Senior approval are shown separately; compilation alone does not establish semantic correctness.</div><div class="cards">${phase42MetricCards(data.metrics, mode, rows)}</div>${rows.map((r, n) => { const finalStatus = r.final_status || 'UNRESOLVED'; const ok = finalStatus === 'APPROVED' || finalStatus === 'QUERY_DEVELOPER_ONLY_COMPLETE'; const statusClass = ok ? 'ok' : 'bad'; const attempts = r.query_developer_attempts || []; const reviews = r.senior_reviews || []; return `<details class="case" ${n===0?'open':''}><summary><b>${esc(r.id)}</b> · ${esc(r.mode)} · ${esc(r.question)} <span class="marker ${statusClass}">${ok ? '✓' : '✖'} ${esc(finalStatus)}</span></summary><div class="case-body"><div class="case-status"><span class="badge">Query Programmer attempts: ${attempts.length}</span><span class="badge ${r.technical_valid ? 'ok':'bad'}">Technical: ${r.technical_valid ? 'OK':'FAIL'}</span><span class="badge ${reviews.some(x => x.status === 'APPROVED') ? 'ok':'bad'}">Senior reviews: ${reviews.length}</span></div><div class="grid">${panel('Functional Analyst', r.functional_analysis)}${panel('Query task', r.query_task)}${panel('Query Programmer attempts', attempts)}${panel('Validation', {first_pass: r.first_pass_validation, final: r.final_validation})}${panel('Senior reviews', reviews)}${phase42Timeline(r.audit_trail)}${panel('Final status', finalStatus)}${panel('Duration (ms)', r.duration_ms)}</div></div></details>`; }).join('') || '<p class="muted">No Phase 4.2 cases found.</p>'}`;
}
function phase42CallPanel(step, event, key=step) {
  const role = event.role || 'event';
  const title = role === 'semantic_clarifier' ? 'Functional Analyst request' : role === 'sqlalchemy_query_developer' ? 'Query Programmer request' : role === 'senior_query_reviewer' ? 'Senior Query Reviewer request' : 'Application validation';
  const note = role === 'query_validation' ? 'Generated by the application, not by the LLM' : `LLM call · ${role}`;
  const base = `phase42-${key}-${Math.random().toString(36).slice(2)}`;
  const metadata = {
    agent_id: event.agent_id,
    prompt_id: event.prompt_id,
    prompt_version: event.prompt_version,
    model: event.model,
    schema_version: event.schema_version,
    latency_ms: event.latency_ms,
  };
  const open = step === 1 ? ' open' : '';
  if (role === 'query_validation') return `<details class="call-step"${open}><summary>Step ${step}: ${esc(title)}</summary><div class="step-body"><div class="muted">${esc(note)}</div>${panel('Input', event.input, '', JSON.stringify(event.input ?? null, null, 2), `${base}-input`, 'Copy input')}${panel('Output', event.output, '', JSON.stringify(event.output ?? null, null, 2), `${base}-output`, 'Copy output')}</div></details>`;
  return `<details class="call-step"${open}><summary>Step ${step}: ${esc(title)}</summary><div class="step-body"><div class="muted">${esc(note)}</div>${panel('Invocation metadata', metadata, '', JSON.stringify(metadata, null, 2), `${base}-metadata`, 'Copy metadata')}${panel('Prompt template', event.prompt || event.prompt_template, '', event.prompt || event.prompt_template || '', `${base}-prompt`, 'Copy prompt')}${panel('Rendered system prompt', event.rendered_system_prompt, '', event.rendered_system_prompt || '', `${base}-rendered-prompt`, 'Copy rendered prompt')}${panel('Rendered messages', event.rendered_messages, '', JSON.stringify(event.rendered_messages ?? [], null, 2), `${base}-messages`, 'Copy messages')}${panel('Input', event.input, '', JSON.stringify(event.input ?? null, null, 2), `${base}-input`, 'Copy input')}${panel('Response', event.output, '', JSON.stringify(event.output ?? null, null, 2), `${base}-response`, 'Copy response')}</div></details>`;
}
function phase42MetricCards(metrics, mode, rows) {
  const card = (label, value) => `<div class="card"><b>${esc(value ?? '—')}</b>${esc(label)}</div>`;
  const cardsFor = (m) => [
    card('Cases', m.cases ?? rows.length),
    card('Executions', m.executions ?? rows.length),
    card('First-pass QUERY', m.query_developer_first_pass_query),
    card('First-pass technically valid', m.query_developer_first_pass_technical_valid),
    card('Technical valid final', m.technical_valid_final),
    card('Senior reviews', m.senior_reviews),
    card('Final approved', m.final_approved),
    card('Revision requested', m.revision_requested),
    card('Repair success', m.repair_success),
    card('Needs clarification', m.needs_clarification_final),
    card('Max revisions', m.max_revisions_reached),
  ].join('');
  const modes = [...new Set(rows.map(row => row.mode).filter(Boolean))];
  if (modes.length > 1) {
    return modes.map(currentMode => {
      const key = currentMode === 'QUERY_DEVELOPER_ONLY' ? 'query_developer_only' : 'agent_team';
      const label = currentMode === 'QUERY_DEVELOPER_ONLY' ? 'Query Developer only' : 'Agent team';
      return `<h3>${label}</h3><div class="cards">${cardsFor(metrics[key] || {})}</div>`;
    }).join('');
  }
  const key = mode === 'QUERY_DEVELOPER_ONLY' ? 'query_developer_only' : 'agent_team';
  return cardsFor(metrics[key] || metrics || {});
}
async function showPhase42Run(i, button) {
  document.querySelectorAll('.run').forEach(x => x.classList.remove('active')); if (button) button.classList.add('active');
  const data = await (await fetch('/api/run?name=' + encodeURIComponent(visibleRuns[i].name))).json();
  const rows = data.rows || [];
  const approved = rows.filter(r => r.final_status === 'APPROVED').length;
  const technical = rows.filter(r => r.technical_valid).length;
  document.getElementById('content').innerHTML = `<h2>${esc(data.name)}</h2><div class="summary-note">Each case is displayed as an ordered execution flow. “Application validation” is deterministic and is not an LLM call.</div><div class="cards">${phase42MetricCards(data.metrics, rows[0] && rows[0].mode, rows)}</div>${rows.map((r, n) => { const finalStatus = r.final_status || 'UNRESOLVED'; const analystOnly = r.mode === 'FUNCTIONAL_ANALYST_ONLY'; const flowComplete = finalStatus === 'APPROVED' || finalStatus === 'QUERY_DEVELOPER_ONLY_COMPLETE' || finalStatus === 'FUNCTIONAL_ANALYST_COMPLETE'; const ok = analystOnly ? finalStatus === 'FUNCTIONAL_ANALYST_COMPLETE' || finalStatus === 'NEEDS_CLARIFICATION' : flowComplete && (finalStatus === 'APPROVED' || r.technical_valid); const statusClass = ok ? 'ok' : 'bad'; return `<details class="case" ${n===0?'open':''}><summary><b>${esc(r.id)}</b> · ${esc(r.mode)} · ${esc(r.question)} <span class="marker ${statusClass}">${ok ? '✓' : '✖'} ${esc(finalStatus)}</span></summary><div class="case-body">${analystOnly ? '' : `<div class="case-status"><span class="badge ${r.technical_valid ? 'ok':'bad'}">Technical: ${r.technical_valid ? 'OK':'FAIL'}</span><span class="badge">Revision count: ${esc(r.revision_count)}</span></div>`}<div class="flow">${(r.audit_trail || []).map((event, index) => phase42CallPanel(index + 1, event)).join('')}</div><div class="grid">${panel('Final status', finalStatus)}${panel('Duration (ms)', r.duration_ms)}</div></div></details>`; }).join('') || '<p class="muted">No Phase 4.2 cases found.</p>'}`;
}
async function showRun(i, button) {
  if (visibleRuns[i] && visibleRuns[i].name.startsWith('direct-sqlalchemy-phase42-')) { showPhase42Run(i, button); return; }
  if (visibleRuns[i] && visibleRuns[i].name.startsWith('semantic-clarifier-')) { showClarifierRun(i, button); return; }
  if (visibleRuns[i] && visibleRuns[i].name.startsWith('semantic-prompt-playground-tests-')) { showPromptRun(i, button); return; }
  document.querySelectorAll('.run').forEach(x => x.classList.remove('active')); if (button) button.classList.add('active');
  const data = await (await fetch('/api/run?name=' + encodeURIComponent(visibleRuns[i].name))).json();
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
            if candidate.parent != RUNS_DIR.resolve() or not candidate.is_dir():
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
            source_rows = _read_jsonl(candidate / "raw_responses.jsonl")
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
