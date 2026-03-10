/**
 * AI Research Agent — Split-Pane App
 * Handles pipeline, editable notebook, chat, save/load/export, and agent re-run.
 */

// ── State ────────────────────────────────────────────────────
let isRunning = false;
let eventSource = null;
let timerInterval = null;
let seconds = 0;
let selectedStage = null;
let rerunStage = null;

// Choice state
let pendingChoice = null;  // { choice_id, type, timeout, timer, remaining }
let choiceCountdownInterval = null;

// Full pipeline state (for save/load/rerun)
const state = {
    topic: "",
    refined_topic: "",
    search_queries: [],
    research_objectives: [],
    methodology_notes: "",
    topic_analysis: "",
    plans: [],
    selected_plan: null,
    papers: [],
    summaries: [],
    synthesis: {},
    gaps: [],
    hypotheses: [],
    hypotheses_raw: [],
    selected_hypothesis: null,
    experiment: { cells: [], explanation: "", requirements: "" },
    execution_outputs: "",
    evaluation: {},
    report: {},
};

// Notebook cells (editable)
let nbCells = [];
let cellCounter = 0;

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

// ── Init ─────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    checkConfig();
    bindEvents();
    initDivider();
});

// ── Events ───────────────────────────────────────────────────
function bindEvents() {
    $("#settings-btn").addEventListener("click", () => $("#settings-modal").classList.remove("hidden"));
    $("#modal-close").addEventListener("click", () => $("#settings-modal").classList.add("hidden"));
    $(".modal-overlay").addEventListener("click", () => $("#settings-modal").classList.add("hidden"));
    $("#save-config-btn").addEventListener("click", saveConfig);
    $$(".preset-btn").forEach(b => b.addEventListener("click", () => {
        $("#base-url-input").value = b.dataset.url;
        $("#model-input").value = b.dataset.model;
    }));

    $("#start-btn").addEventListener("click", startResearch);
    $("#topic-input").addEventListener("keydown", e => { if (e.key === "Enter" && !isRunning) startResearch(); });

    // Pipeline stage clicks
    $$(".stage-item").forEach(item => item.addEventListener("click", () => selectStage(item.dataset.stage)));

    // Re-run buttons
    $$(".rerun-btn").forEach(btn => btn.addEventListener("click", e => {
        e.stopPropagation();
        openRerunPanel(btn.dataset.stage);
    }));
    $("#rerun-submit-btn").addEventListener("click", submitRerun);

    // Chat
    $("#chat-send-btn").addEventListener("click", sendChat);
    $("#chat-input").addEventListener("keydown", e => { if (e.key === "Enter") sendChat(); });

    // Notebook controls
    $("#btn-add-cell").addEventListener("click", () => addEmptyCell());
    $("#btn-run-all").addEventListener("click", runAllCells);

    // Canvas save button
    $("#btn-save-agent").addEventListener("click", saveAgentOutput);

    // Toolbar
    $("#btn-save").addEventListener("click", saveProgress);
    $("#btn-load").addEventListener("click", () => $("#load-file-input").click());
    $("#load-file-input").addEventListener("change", loadProgress);
    $("#btn-export-docx").addEventListener("click", exportDocx);
    $("#btn-export-ipynb").addEventListener("click", exportIpynb);
    $("#btn-export-md").addEventListener("click", exportMarkdown);
}

// ── Config ───────────────────────────────────────────────────
async function checkConfig() {
    try {
        const r = await fetch("/api/config/status");
        const d = await r.json();
        updateBadge(d.is_configured);
        if (d.has_api_key) {
            $("#base-url-input").value = d.openai_base_url;
            $("#model-input").value = d.openai_model;
            $("#papers-input").value = d.max_papers;
        }
    } catch (e) { }
}
function updateBadge(ok) {
    const b = $("#config-status");
    b.className = ok ? "config-badge configured" : "config-badge not-configured";
    b.querySelector(".label").textContent = ok ? "Configured" : "Not Configured";
}
async function saveConfig() {
    const key = $("#api-key-input").value.trim();
    const st = $("#save-status");
    if (!key) { st.textContent = "Key required"; st.className = "save-status error"; return; }
    try {
        const r = await fetch("/api/config", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                openai_api_key: key,
                openai_base_url: $("#base-url-input").value.trim() || "https://api.openai.com/v1",
                openai_model: $("#model-input").value.trim() || "gpt-4o-mini",
                max_papers: parseInt($("#papers-input").value) || 8,
            }),
        });
        const d = await r.json();
        if (d.is_configured) {
            st.textContent = "Saved!"; st.className = "save-status success";
            updateBadge(true);
            setTimeout(() => $("#settings-modal").classList.add("hidden"), 800);
        }
    } catch (e) { st.textContent = "Failed"; st.className = "save-status error"; }
}

// ── Pane Divider ─────────────────────────────────────────────
function initDivider() {
    const div = $("#pane-divider");
    const left = $("#left-pane");
    let dragging = false, startX, startW;

    div.addEventListener("mousedown", e => {
        dragging = true; startX = e.clientX; startW = left.offsetWidth;
        div.classList.add("dragging");
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
    });
    document.addEventListener("mousemove", e => {
        if (!dragging) return;
        const w = Math.max(240, Math.min(700, startW + (e.clientX - startX)));
        left.style.width = w + "px";
    });
    document.addEventListener("mouseup", () => {
        if (dragging) {
            dragging = false;
            div.classList.remove("dragging");
            document.body.style.cursor = "";
            document.body.style.userSelect = "";
        }
    });
}

// ── Research Pipeline ────────────────────────────────────────
function startResearch() {
    const topic = $("#topic-input").value.trim();
    if (!topic || topic.length < 3) { alert("Enter a topic (3+ chars)."); return; }
    if (isRunning) return;
    isRunning = true;
    state.topic = topic;

    resetAll();
    $("#start-btn").disabled = true;
    $(".btn-text").textContent = "Running...";
    $("#topic-input").disabled = true;
    startTimer();

    eventSource = new EventSource(`/api/research/start?topic=${encodeURIComponent(topic)}`);
    eventSource.onmessage = ev => {
        try { handleEvent(JSON.parse(ev.data)); } catch (e) { console.error(e); }
    };
    eventSource.onerror = () => { eventSource.close(); finish(true); };
}

function resetAll() {
    ["planner", "paper_reader", "hypothesis_gen", "experiment", "evaluation", "writer"].forEach(s => {
        $(`#ind-${s}`).className = "stage-indicator";
    });
    selectedStage = null;
    updateCanvasView();
    $("#rerun-panel").classList.add("hidden");
    $("#chat-messages").innerHTML = "";
    nbCells = [];
    cellCounter = 0;
    renderNotebook();
    seconds = 0;
    updateTimer();
    // Reset state
    Object.keys(state).forEach(k => {
        if (Array.isArray(state[k])) state[k] = [];
        else if (typeof state[k] === "object" && state[k] !== null) state[k] = {};
        else if (typeof state[k] === "string") state[k] = "";
    });
    state.topic = $("#topic-input").value.trim();
}

function handleEvent(ev) {
    const { stage, status, message, data } = ev;

    if (stage === "done") { finish(status === "error"); return; }

    // Update indicator
    const ind = $(`#ind-${stage}`);
    if (ind) {
        if (["starting", "progress", "notebook_ready", "cell_running", "choice_required"].includes(status)) ind.className = "stage-indicator running";
        else if (["completed", "cell_completed"].includes(status)) ind.className = "stage-indicator completed";
        else if (["error", "cell_error"].includes(status)) ind.className = "stage-indicator error";
    }

    // Store data in state
    if (data) storeStageData(stage, status, data);

    // Handle choice_required — show selection cards
    if (status === "choice_required" && data) {
        handleChoiceRequired(stage, data);
    }

    // Notebook events
    if (stage === "experiment") {
        handleNotebookEvent(status, data);
    }

    // Auto-select current stage
    if (status === "starting" || status === "choice_required") selectStage(stage);
    if (status === "completed" || status === "error") {
        clearChoiceCountdown();
        updateSelectedDetail();
    }
}

function storeStageData(stage, status, data) {
    if (stage === "planner" && status === "choice_required") {
        state.topic_analysis = data.topic_analysis || "";
        state.plans = data.plans || [];
    }
    if (stage === "planner" && status === "completed") {
        state.selected_plan = data.selected_plan || null;
        state.refined_topic = data.refined_topic || "";
        state.search_queries = data.search_queries || [];
        state.research_objectives = data.research_objectives || [];
        state.methodology_notes = data.methodology_notes || "";
    }
    if (stage === "paper_reader" && status === "completed") {
        state.papers = data.papers || [];
        state.summaries = data.summaries || [];
        state.synthesis = data.synthesis || {};
    }
    if (stage === "hypothesis_gen" && status === "choice_required") {
        state.gaps = data.gaps || [];
        state.hypotheses = data.hypotheses || [];
        state.hypotheses_raw = data.hypotheses_raw || [];
    }
    if (stage === "hypothesis_gen" && status === "completed") {
        state.gaps = data.gaps || state.gaps;
        state.hypotheses = data.hypotheses || state.hypotheses;
        state.selected_hypothesis = data.selected_hypothesis || null;
    }
    if (stage === "experiment") {
        if (status === "notebook_ready") {
            state.experiment = { cells: data.cells || [], explanation: data.explanation || "", requirements: data.requirements || "" };
        }
        if (status === "completed" && data.execution_summary) {
            state.execution_outputs = data.execution_summary;
        }
    }
    if (stage === "evaluation" && status === "completed") {
        state.evaluation = data;
    }
    if (stage === "writer" && status === "completed") {
        state.report = data;
    }
}

// ── User Choice Handling ─────────────────────────────────────
function handleChoiceRequired(stage, data) {
    const choiceId = data.choice_id;
    const timeout = data.timeout || 300;
    const type = data.choice_type; // 'plan' or 'hypothesis'

    pendingChoice = { choice_id: choiceId, type, timeout, remaining: timeout };
    startChoiceCountdown();
    updateSelectedDetail();
}

function startChoiceCountdown() {
    clearChoiceCountdown();
    choiceCountdownInterval = setInterval(() => {
        if (!pendingChoice) { clearChoiceCountdown(); return; }
        pendingChoice.remaining--;
        updateChoiceTimerDisplay();
        if (pendingChoice.remaining <= 0) {
            clearChoiceCountdown();
            // Timeout reached — pipeline auto-selects on backend
            pendingChoice = null;
        }
    }, 1000);
}

function clearChoiceCountdown() {
    if (choiceCountdownInterval) {
        clearInterval(choiceCountdownInterval);
        choiceCountdownInterval = null;
    }
}

function updateChoiceTimerDisplay() {
    const timerEl = $("#choice-timer");
    if (timerEl && pendingChoice) {
        const m = Math.floor(pendingChoice.remaining / 60).toString().padStart(2, '0');
        const s = (pendingChoice.remaining % 60).toString().padStart(2, '0');
        timerEl.textContent = `Auto-selects in ${m}:${s}`;
    }
}

async function submitChoice(index) {
    if (!pendingChoice) return;
    clearChoiceCountdown();

    try {
        await fetch("/api/choice", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ choice_id: pendingChoice.choice_id, selected_index: index }),
        });
    } catch (e) {
        console.error("Choice submission failed:", e);
    }

    pendingChoice = null;
    // UI will update when pipeline sends the 'completed' event
}

// ── Notebook Events ──────────────────────────────────────────
function handleNotebookEvent(status, data) {
    if (status === "notebook_ready" && data?.cells) {
        nbCells = data.cells.map((c, i) => ({
            id: c.cell_id || `cell_${i}`,
            title: c.title || `Cell ${i + 1}`,
            code: c.code || "",
            description: c.description || "",
            output: "", error: "", images: [], time: 0, status: "waiting",
        }));
        cellCounter = nbCells.length;
        renderNotebook();
        $("#notebook-status").textContent = "Executing...";
    }
    if (status === "cell_running" && data?.cell_id) {
        const c = nbCells.find(x => x.id === data.cell_id);
        if (c) { c.status = "running"; updateCellUI(c.id); }
    }
    if (status === "cell_completed" && data) {
        applyCellResult(data, "success");
    }
    if (status === "cell_error" && data) {
        applyCellResult(data, "error");
    }
    if (status === "completed") {
        $("#notebook-status").textContent = "Complete";
    }
}

function applyCellResult(data, st) {
    const c = nbCells.find(x => x.id === data.cell_id);
    if (!c) return;
    c.output = data.stdout || "";
    c.error = data.error || data.stderr || "";
    c.images = data.images || [];
    c.time = data.execution_time || 0;
    c.status = st;
    updateCellUI(c.id);
}

// ── Render Notebook ──────────────────────────────────────────
function renderNotebook() {
    const container = $("#notebook-cells");
    if (nbCells.length === 0) {
        container.innerHTML = `<div class="nb-empty-state">
            <p>&#x1F52C; Start a research session to see notebook cells here.</p>
            <p class="nb-empty-sub">Or click "+ Add Cell" to create your own.</p></div>`;
        return;
    }
    container.innerHTML = "";
    nbCells.forEach((c, i) => container.appendChild(buildCellEl(c, i)));
    // Add "add cell" area at bottom
    const add = document.createElement("div");
    add.className = "nb-add-cell";
    add.innerHTML = "+ Add Cell";
    add.addEventListener("click", () => addEmptyCell());
    container.appendChild(add);
}

function buildCellEl(cell, index) {
    const el = document.createElement("div");
    el.className = "nb-cell";
    el.id = `nb-${cell.id}`;

    el.innerHTML = `
        <div class="nb-cell-bar">
            <span class="nb-cell-num">In [${index + 1}]</span>
            <input class="nb-cell-title-input" value="${esc(cell.title)}" data-id="${cell.id}" placeholder="Cell title...">
            <span class="nb-cell-time">${cell.time ? cell.time.toFixed(1) + 's' : ''}</span>
            <span class="nb-cell-badge ${cell.status}">${cell.status}</span>
            <div class="nb-cell-actions">
                <button class="nb-act-btn run-btn" title="Run" data-id="${cell.id}">&#x25B6;</button>
                <button class="nb-act-btn del-btn" title="Delete" data-id="${cell.id}">&#x2715;</button>
            </div>
        </div>
        <div class="nb-cell-code-wrap">
            <textarea class="nb-cell-code" data-id="${cell.id}" spellcheck="false" placeholder="# Write Python code here...">${esc(cell.code)}</textarea>
        </div>
        ${cell.output ? `<div class="nb-cell-output"><pre>${esc(cell.output)}</pre></div>` : ''}
        ${cell.error ? `<div class="nb-cell-output has-error"><pre>${esc(cell.error)}</pre></div>` : ''}
        ${cell.images?.length ? `<div class="nb-cell-images">${cell.images.map(b => `<img src="data:image/png;base64,${b}">`).join('')}</div>` : ''}
    `;

    // Event listeners
    const textarea = el.querySelector(".nb-cell-code");
    textarea.addEventListener("input", () => {
        cell.code = textarea.value;
        autoResize(textarea);
    });
    textarea.addEventListener("keydown", e => {
        if (e.key === "Tab") { e.preventDefault(); insertTab(textarea); }
    });
    setTimeout(() => autoResize(textarea), 0);

    const titleInput = el.querySelector(".nb-cell-title-input");
    titleInput.addEventListener("input", () => { cell.title = titleInput.value; });

    el.querySelector(".run-btn").addEventListener("click", e => { e.stopPropagation(); runCell(cell.id); });
    el.querySelector(".del-btn").addEventListener("click", e => { e.stopPropagation(); deleteCell(cell.id); });

    return el;
}

function autoResize(ta) {
    ta.style.height = "auto";
    ta.style.height = Math.max(60, ta.scrollHeight) + "px";
}

function insertTab(ta) {
    const start = ta.selectionStart, end = ta.selectionEnd;
    ta.value = ta.value.substring(0, start) + "    " + ta.value.substring(end);
    ta.selectionStart = ta.selectionEnd = start + 4;
    ta.dispatchEvent(new Event("input"));
}

function updateCellUI(cellId) {
    const cell = nbCells.find(c => c.id === cellId);
    if (!cell) return;
    const idx = nbCells.indexOf(cell);
    const oldEl = $(`#nb-${cellId}`);
    if (!oldEl) return;
    const newEl = buildCellEl(cell, idx);
    oldEl.replaceWith(newEl);
}

// ── Cell Operations ──────────────────────────────────────────
function addEmptyCell() {
    cellCounter++;
    const cell = {
        id: `user_cell_${cellCounter}_${Date.now()}`,
        title: `Cell ${cellCounter}`,
        code: "",
        description: "",
        output: "", error: "", images: [], time: 0, status: "waiting",
    };
    nbCells.push(cell);
    renderNotebook();
    // Focus the new cell
    setTimeout(() => {
        const ta = $(`#nb-${cell.id} .nb-cell-code`);
        if (ta) ta.focus();
    }, 50);
}

function deleteCell(cellId) {
    nbCells = nbCells.filter(c => c.id !== cellId);
    renderNotebook();
}

async function runCell(cellId) {
    const cell = nbCells.find(c => c.id === cellId);
    if (!cell) return;

    // Read latest code from textarea
    const ta = $(`#nb-${cellId} .nb-cell-code`);
    if (ta) cell.code = ta.value;

    cell.status = "running";
    cell.output = ""; cell.error = ""; cell.images = [];
    updateCellUI(cellId);

    try {
        const r = await fetch("/api/notebook/execute", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code: cell.code, timeout: 300 }),
        });
        const d = await r.json();
        cell.output = d.stdout || "";
        cell.error = d.error || d.stderr || "";
        cell.images = d.images || [];
        cell.time = d.execution_time || 0;
        cell.status = d.success ? "success" : "error";
    } catch (e) {
        cell.error = "Request failed: " + e.message;
        cell.status = "error";
    }
    updateCellUI(cellId);
}

async function runAllCells() {
    for (const cell of nbCells) {
        await runCell(cell.id);
    }
}

// ── Stage Selection & Detail ─────────────────────────────────
function selectStage(stage) {
    selectedStage = stage;
    $$(".stage-item").forEach(s => s.classList.toggle("selected", s.dataset.stage === stage));
    updateCanvasView();
    // Hide rerun panel when switching
    $("#rerun-panel").classList.add("hidden");
}

function updateCanvasView() {
    const canvasView = $("#canvas-view");
    const notebookView = $("#notebook-view");
    const canvasTitle = $("#canvas-title");
    const notebookControls = $("#notebook-controls");
    const saveBtn = $("#btn-save-agent");
    const chatLabel = $("#chat-agent-label");

    const labels = {
        planner: "🧠 Planner Agent",
        paper_reader: "📚 Paper Reader Agent",
        hypothesis_gen: "🔬 Hypothesis Agent",
        experiment: "⚗️ Experiment Notebook",
        evaluation: "📊 Evaluation Agent",
        writer: "📝 Writer Agent",
    };
    const chatLabels = {
        planner: "💬 Planner",
        paper_reader: "💬 Paper Reader",
        hypothesis_gen: "💬 Hypothesis",
        experiment: "💬 Experiment",
        evaluation: "💬 Evaluation",
        writer: "💬 Writer",
    };

    if (!selectedStage) {
        canvasView.style.display = "";
        notebookView.style.display = "none";
        notebookControls.style.display = "none";
        saveBtn.style.display = "none";
        canvasTitle.textContent = "📓 Canvas";
        canvasView.innerHTML = `<div class="canvas-empty-state">
            <p>🔬 Click a pipeline stage to see its output here.</p>
            <p class="nb-empty-sub">Start a research session to begin.</p></div>`;
        if (chatLabel) chatLabel.textContent = "Select a stage";
        return;
    }

    canvasTitle.textContent = labels[selectedStage] || "Canvas";
    if (chatLabel) chatLabel.textContent = chatLabels[selectedStage] || "Select a stage";

    // For Experiment: show notebook, hide canvas, show notebook controls
    if (selectedStage === "experiment") {
        canvasView.style.display = "none";
        notebookView.style.display = "";
        notebookControls.style.display = "";
        saveBtn.style.display = "";
        saveBtn.textContent = "💾 Export .ipynb";
    } else {
        canvasView.style.display = "";
        notebookView.style.display = "none";
        notebookControls.style.display = "none";
        saveBtn.style.display = "";
        saveBtn.textContent = "💾 Save Output";
        renderCanvasContent();
    }
}

function updateSelectedDetail() {
    updateCanvasView();
}

// ── Render agent output in the RIGHT PANE canvas ─────────────
function renderCanvasContent() {
    const el = $("#canvas-view");
    if (!selectedStage) return;

    switch (selectedStage) {
        case "planner": el.innerHTML = renderPlannerCanvas(); break;
        case "paper_reader": el.innerHTML = renderPaperCanvas(); break;
        case "hypothesis_gen": el.innerHTML = renderHypoCanvas(); break;
        case "evaluation": el.innerHTML = renderEvalCanvas(); break;
        case "writer": el.innerHTML = renderWriterCanvas(); break;
        default: el.innerHTML = "";
    }
}

function renderPlannerDetail() {
    // If we have pending plans to choose from, show choice cards
    if (pendingChoice && pendingChoice.type === 'plan' && state.plans.length) {
        return renderPlanChoiceCards();
    }
    // After selection, show selected plan
    if (state.selected_plan) {
        const p = state.selected_plan;
        return `<div class="detail-block" style="border-left-color:var(--green);">
            <h4>✓ Selected: ${esc(p.title)}</h4>
            <p>${esc(p.description || '')}</p>
            <p style="color:var(--cyan);margin-top:4px;">Methodology: ${esc(p.methodology || '')}</p></div>
            <div class="detail-block"><h4>Search Queries</h4>${(p.search_queries || state.search_queries).map(q => `<p>• ${esc(q)}</p>`).join('')}</div>`;
    }
    if (state.refined_topic) {
        return `<div class="detail-block"><h4>Refined Topic</h4><p>${esc(state.refined_topic)}</p></div>
            <div class="detail-block"><h4>Search Queries</h4>${state.search_queries.map(q => `<p>• ${esc(q)}</p>`).join('')}</div>`;
    }
    return '<div class="detail-block">Waiting for planner...</div>';
}

function renderPlanChoiceCards() {
    let html = '';
    if (state.topic_analysis) {
        html += `<div class="detail-block"><h4>Topic Analysis</h4><p>${esc(state.topic_analysis)}</p></div>`;
    }
    html += `<div class="choice-countdown" id="choice-timer">Auto-selects in 05:00</div>`;
    html += '<div class="choice-cards">';
    state.plans.forEach((p, i) => {
        const n = p.novelty_score || 5, f = p.feasibility_score || 5, im = p.impact_score || 5;
        html += `<div class="choice-card" onclick="submitChoice(${i})">
            <div class="choice-card-header">
                <span class="choice-card-num">Plan ${i + 1}</span>
                <div class="choice-scores">
                    <span class="score-pill novelty">N:${n}</span>
                    <span class="score-pill feasibility">F:${f}</span>
                    <span class="score-pill impact">I:${im}</span>
                </div>
            </div>
            <h4 class="choice-card-title">${esc(p.title)}</h4>
            <p class="choice-card-desc">${esc(p.description || '')}</p>
            <p class="choice-card-method">Methodology: ${esc(p.methodology || '')}</p>
            <div class="choice-card-footer">
                <span class="choice-pro">✓ ${esc(p.pros || '')}</span>
                <span class="choice-con">⚠ ${esc(p.cons || '')}</span>
            </div>
        </div>`;
    });
    html += '</div>';
    return html;
}

function renderPaperDetail() {
    if (!state.papers.length) return '<div class="detail-block">Waiting for papers...</div>';
    let html = `<div class="detail-block"><h4>Papers (${state.papers.length})</h4></div>`;
    if (state.synthesis && state.synthesis.synthesis) {
        html += `<div class="detail-block"><h4>Literature Synthesis</h4><p>${esc(state.synthesis.synthesis)}</p></div>`;
    }
    html += state.papers.map((p, i) => {
        const s = state.summaries[i] || {};
        return `<div class="paper-item"><div class="paper-title">${esc(p.title)}</div>
                <div class="paper-meta">${esc((p.authors || []).slice(0, 2).join(', '))} | ${esc(p.published || '')}</div>
                <div style="font-size:0.75rem;color:var(--text-3);margin-top:3px;">Dataset: ${esc(s.dataset_used || 'N/A')} | Results: ${esc(s.evaluation_results || 'N/A')}</div>
            </div>`;
    }).join('');
    return html;
}

function renderHypoDetail() {
    // If we have pending hypotheses to choose from, show choice cards
    if (pendingChoice && pendingChoice.type === 'hypothesis' && state.hypotheses.length) {
        return renderHypothesisChoiceCards();
    }
    if (!state.hypotheses.length) return '<div class="detail-block">Waiting for hypothesis...</div>';
    let html = '';
    if (state.gaps.length) {
        html += `<div class="detail-block"><h4>Gaps (${state.gaps.length})</h4>
            ${state.gaps.map(g => `<p style="margin-bottom:4px;">• ${esc(g.description)}</p>`).join('')}</div>`;
    }
    state.hypotheses.forEach((h, i) => {
        const sel = state.selected_hypothesis && h.title === state.selected_hypothesis.title;
        html += `<div class="detail-block" style="${sel ? 'border-left-color:var(--green);' : ''}">
            <h4>${sel ? '✓ SELECTED: ' : ''}${esc(h.title)}</h4>
            <p>${esc(h.description)}</p>
            <p style="color:var(--cyan);margin-top:3px;">Approach: ${esc(h.proposed_approach)}</p></div>`;
    });
    return html;
}

function renderHypothesisChoiceCards() {
    let html = '';
    if (state.gaps.length) {
        html += `<div class="detail-block"><h4>Research Gaps (${state.gaps.length})</h4>
            ${state.gaps.map(g => `<p style="margin-bottom:4px;">• ${esc(g.description)}</p>`).join('')}</div>`;
    }
    html += `<div class="choice-countdown" id="choice-timer">Auto-selects in 05:00</div>`;
    html += '<div class="choice-cards">';
    const raw = state.hypotheses_raw || [];
    state.hypotheses.forEach((h, i) => {
        const r = raw[i] || {};
        const n = r.novelty_score || 5, f = r.feasibility_score || 5, im = r.impact_score || 5;
        html += `<div class="choice-card" onclick="submitChoice(${i})">
            <div class="choice-card-header">
                <span class="choice-card-num">Hypothesis ${i + 1}</span>
                <div class="choice-scores">
                    <span class="score-pill novelty">N:${n}</span>
                    <span class="score-pill feasibility">F:${f}</span>
                    <span class="score-pill impact">I:${im}</span>
                </div>
            </div>
            <h4 class="choice-card-title">${esc(h.title)}</h4>
            <p class="choice-card-desc">${esc(h.description)}</p>
            <p class="choice-card-method">Approach: ${esc(h.proposed_approach)}</p>
            <p class="choice-card-outcome">Expected: ${esc(h.expected_outcome || '')}</p>
        </div>`;
    });
    html += '</div>';
    return html;
}
function renderExpDetail() {
    if (!state.experiment.cells?.length) return '<div class="detail-block">Waiting for experiment...</div>';
    return `<div class="detail-block"><h4>Experiment</h4><p>${esc(state.experiment.explanation)}</p>
        <p style="margin-top:4px;color:var(--text-3);">${state.experiment.cells.length} cells generated. See notebook canvas →</p></div>`;
}
function renderEvalDetail() {
    if (!state.evaluation.estimated_accuracy) return '<div class="detail-block">Waiting for evaluation...</div>';
    const e = state.evaluation;
    return `<div class="metric-grid">
            <div class="metric-item"><div class="metric-label">Accuracy</div><div class="metric-value">${esc(e.estimated_accuracy)}</div></div>
            <div class="metric-item"><div class="metric-label">F1</div><div class="metric-value">${esc(e.estimated_f1)}</div></div>
            <div class="metric-item"><div class="metric-label">Precision</div><div class="metric-value">${esc(e.estimated_precision)}</div></div>
            <div class="metric-item"><div class="metric-label">Recall</div><div class="metric-value">${esc(e.estimated_recall)}</div></div>
        </div>
        <div class="detail-block" style="margin-top:8px;"><h4>Assessment</h4><p>${esc(e.overall_assessment)}</p></div>
        <div class="detail-block"><h4>Strengths</h4><p style="color:var(--green);">${esc(e.strengths)}</p></div>
        <div class="detail-block"><h4>Limitations</h4><p style="color:var(--amber);">${esc(e.limitations)}</p></div>`;
}
function renderWriterDetail() {
    if (!state.report.title) return '<div class="detail-block">Waiting for report...</div>';
    const r = state.report;
    const secs = ['abstract', 'introduction', 'literature_review', 'methodology', 'experiment_setup', 'results', 'discussion', 'conclusion', 'references'];
    return `<div class="detail-block"><h4>${esc(r.title)}</h4></div>
        ${secs.map(k => r[k] ? `<div class="report-sec"><h5>${k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</h5><p>${esc(r[k])}</p></div>` : '').join('')}`;
}

// Canvas aliases for right-pane rendering
const renderPlannerCanvas = renderPlannerDetail;
const renderPaperCanvas = renderPaperDetail;
const renderHypoCanvas = renderHypoDetail;
const renderEvalCanvas = renderEvalDetail;
const renderWriterCanvas = renderWriterDetail;

// ── Re-run Agent ─────────────────────────────────────────────
function openRerunPanel(stage) {
    rerunStage = stage;
    selectStage(stage);
    $("#rerun-panel").classList.remove("hidden");
    $("#rerun-feedback").value = "";
    $("#rerun-feedback").focus();
}

async function submitRerun() {
    if (!rerunStage) return;
    const feedback = $("#rerun-feedback").value.trim();
    const btn = $("#rerun-submit-btn");
    btn.textContent = "Re-running...";
    btn.disabled = true;

    // Set indicator to running
    $(`#ind-${rerunStage}`).className = "stage-indicator running";

    try {
        const r = await fetch("/api/agent/rerun", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ stage: rerunStage, feedback, current_state: state }),
        });
        const d = await r.json();
        if (d.status === "ok") {
            // Apply new data
            storeStageData(rerunStage, "completed", d.data);
            $(`#ind-${rerunStage}`).className = "stage-indicator completed";

            // If experiment, update notebook
            if (rerunStage === "experiment" && d.data?.cells) {
                nbCells = d.data.cells.map((c, i) => ({
                    id: c.cell_id || `cell_${i}`,
                    title: c.title || `Cell ${i + 1}`,
                    code: c.code || "",
                    description: c.description || "",
                    output: "", error: "", images: [], time: 0, status: "waiting",
                }));
                cellCounter = nbCells.length;
                renderNotebook();
            }

            updateSelectedDetail();
        } else {
            $(`#ind-${rerunStage}`).className = "stage-indicator error";
        }
    } catch (e) {
        alert("Re-run failed: " + e.message);
        $(`#ind-${rerunStage}`).className = "stage-indicator error";
    }

    btn.textContent = "Re-run Agent";
    btn.disabled = false;
    $("#rerun-panel").classList.add("hidden");
}

// ── Agent-Specific Chat ──────────────────────────────────────
async function sendChat() {
    const inp = $("#chat-input");
    const msg = inp.value.trim();
    if (!msg) return;
    inp.value = "";

    const agentNames = {
        planner: "Planner", paper_reader: "Paper Reader",
        hypothesis_gen: "Hypothesis", experiment: "Experiment",
        evaluation: "Evaluation", writer: "Writer",
    };
    const agentName = agentNames[selectedStage] || "Agent";
    addBubble("user", msg);

    // Build agent-specific context
    let ctx = `Topic: ${state.topic}\nYou are the ${agentName} Agent. `;
    if (selectedStage === "planner") {
        ctx += `Plans generated: ${state.plans.length}. Selected: ${state.selected_plan?.title || 'none'}. `;
        ctx += `Topic analysis: ${state.topic_analysis?.substring(0, 500) || ''}`;
    } else if (selectedStage === "paper_reader") {
        ctx += `Papers read: ${state.papers.length}. `;
        state.papers.slice(0, 5).forEach(p => { ctx += `Paper: ${p.title}. `; });
        if (state.synthesis?.synthesis) ctx += `Synthesis: ${state.synthesis.synthesis.substring(0, 500)}`;
    } else if (selectedStage === "hypothesis_gen") {
        ctx += `Gaps: ${state.gaps.length}. Hypotheses: ${state.hypotheses.length}. `;
        ctx += `Selected: ${state.selected_hypothesis?.title || 'none'}. `;
        state.hypotheses.forEach(h => { ctx += `H: ${h.title} — ${h.description?.substring(0, 100)}. `; });
    } else if (selectedStage === "experiment") {
        ctx += `Cells: ${nbCells.length}. `;
        nbCells.forEach(c => { if (c.output) ctx += `[${c.title}]: ${c.output.substring(0, 300)}\n`; });
    } else if (selectedStage === "evaluation") {
        ctx += `Accuracy: ${state.evaluation.estimated_accuracy || 'N/A'}. Assessment: ${state.evaluation.overall_assessment?.substring(0, 500) || ''}`;
    } else if (selectedStage === "writer") {
        ctx += `Report title: ${state.report.title || 'N/A'}. Sections generated. `;
    }

    // Instruct the LLM about dual behavior
    const taskInstruction = `\n\nIMPORTANT: If the user asks a question, answer it directly.
If the user asks you to PERFORM a task (generate content, write code, rewrite sections, add papers, etc.), 
wrap the task output between [CANVAS_START] and [CANVAS_END] markers. The content inside these markers
will be displayed in the main canvas area. You can also include a brief chat message outside the markers.`;

    try {
        const r = await fetch("/api/notebook/chat", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: msg,
                context: ctx.substring(0, 5500) + taskInstruction,
                agent: selectedStage || "general",
            }),
        });
        const d = await r.json();

        if (!r.ok) {
            addBubble("assistant", "⚠️ Error: " + (d.detail || d.message || "Request failed"), agentName);
            return;
        }

        const responseText = d.response || "";

        // Check for canvas action markers
        const canvasMatch = responseText.match(/\[CANVAS_START\]([\s\S]*?)\[CANVAS_END\]/);
        if (canvasMatch) {
            // Extract canvas content and chat message
            const canvasContent = canvasMatch[1].trim();
            const chatMessage = responseText.replace(/\[CANVAS_START\][\s\S]*?\[CANVAS_END\]/, '').trim();

            if (chatMessage) {
                addBubble("assistant", chatMessage, agentName);
            } else {
                addBubble("assistant", "✅ Output updated in canvas →", agentName);
            }

            // Render canvas content
            renderChatCanvasOutput(canvasContent, agentName);
        } else {
            addBubble("assistant", responseText, agentName);
        }
    } catch (e) {
        addBubble("assistant", "⚠️ Network error: " + e.message, agentName);
    }
}

function renderChatCanvasOutput(content, agentName) {
    const canvasView = $("#canvas-view");
    if (!canvasView || selectedStage === "experiment") return;

    // Format the content for display
    let html = `<div class="detail-block" style="border-left-color:var(--cyan);">
        <h4>💬 ${agentName} — Chat Response</h4></div>`;

    // Handle code blocks
    let formatted = esc(content);
    formatted = formatted.replace(/```(\w*)\n([\s\S]*?)```/g,
        '<pre style="background:rgba(0,0,0,0.3);padding:12px;border-radius:6px;overflow-x:auto;font-family:var(--mono);font-size:0.82rem;margin:8px 0;">$2</pre>');
    formatted = formatted.replace(/\n/g, '<br>');

    html += `<div class="detail-block"><div style="line-height:1.6;">${formatted}</div></div>`;

    // Prepend to canvas (keep existing content below)
    const wrapper = document.createElement("div");
    wrapper.className = "canvas-chat-output";
    wrapper.style.cssText = "border-bottom:1px solid var(--border-dim);padding-bottom:12px;margin-bottom:12px;animation:fadeIn 0.3s ease;";
    wrapper.innerHTML = html;
    canvasView.insertBefore(wrapper, canvasView.firstChild);
}

function addBubble(role, content, agentName) {
    const box = $("#chat-messages");
    const div = document.createElement("div");
    div.className = `chat-msg ${role}`;
    let formatted = esc(content);
    formatted = formatted.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre>$2</pre>');
    formatted = formatted.replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,0.05);padding:1px 3px;border-radius:2px;font-family:var(--mono);font-size:0.8em;">$1</code>');
    const sender = role === "user" ? "You" : (agentName || "Agent");
    div.innerHTML = `<div class="chat-sender">${sender}</div><div class="chat-bubble">${formatted}</div>`;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

// ── Save Agent Output ────────────────────────────────────────
function saveAgentOutput() {
    if (!selectedStage) return;

    if (selectedStage === "experiment") {
        exportIpynb();
        return;
    }

    const agentNames = {
        planner: "planner", paper_reader: "paper_reader",
        hypothesis_gen: "hypothesis", evaluation: "evaluation", writer: "writer",
    };
    const name = agentNames[selectedStage] || selectedStage;
    let content = "";

    if (selectedStage === "planner") {
        content += `= PLANNER AGENT OUTPUT =\nTopic: ${state.topic}\n`;
        if (state.topic_analysis) content += `\nTopic Analysis:\n${state.topic_analysis}\n`;
        if (state.selected_plan) {
            content += `\nSelected Plan: ${state.selected_plan.title}\n`;
            content += `Description: ${state.selected_plan.description || ''}\n`;
            content += `Methodology: ${state.selected_plan.methodology || ''}\n`;
        }
        state.plans.forEach((p, i) => {
            content += `\n--- Plan ${i + 1}: ${p.title} ---\n`;
            content += `Description: ${p.description || ''}\nMethodology: ${p.methodology || ''}\n`;
            content += `Pros: ${p.pros || ''}\nCons: ${p.cons || ''}\n`;
            content += `Scores: N=${p.novelty_score || 'N/A'} F=${p.feasibility_score || 'N/A'} I=${p.impact_score || 'N/A'}\n`;
        });
        if (state.search_queries?.length) content += `\nSearch Queries:\n${state.search_queries.map(q => `  - ${q}`).join('\n')}\n`;
    } else if (selectedStage === "paper_reader") {
        content += `= PAPER READER AGENT OUTPUT =\n\nPapers Read: ${state.papers.length}\n`;
        state.papers.forEach((p, i) => {
            const s = state.summaries[i] || {};
            content += `\n--- Paper ${i + 1} ---\nTitle: ${p.title}\nAuthors: ${(p.authors || []).join(', ')}\n`;
            content += `Published: ${p.published || ''}\nProblem: ${s.problem_statement || ''}\n`;
            content += `Method: ${s.proposed_method || ''}\nDataset: ${s.dataset_used || ''}\n`;
            content += `Results: ${s.evaluation_results || ''}\nLimitations: ${s.limitations || ''}\n`;
        });
        if (state.synthesis?.synthesis) content += `\n= LITERATURE SYNTHESIS =\n${state.synthesis.synthesis}\n`;
    } else if (selectedStage === "hypothesis_gen") {
        content += `= HYPOTHESIS AGENT OUTPUT =\n`;
        if (state.gaps.length) {
            content += `\nResearch Gaps (${state.gaps.length}):\n`;
            state.gaps.forEach((g, i) => { content += `  ${i + 1}. ${g.description}\n`; });
        }
        state.hypotheses.forEach((h, i) => {
            const sel = state.selected_hypothesis && h.title === state.selected_hypothesis.title;
            content += `\n--- Hypothesis ${i + 1}${sel ? ' [SELECTED]' : ''} ---\n`;
            content += `Title: ${h.title}\nDescription: ${h.description}\nApproach: ${h.proposed_approach}\n`;
            content += `Expected Outcome: ${h.expected_outcome || ''}\n`;
        });
    } else if (selectedStage === "evaluation") {
        const e = state.evaluation;
        content += `= EVALUATION AGENT OUTPUT =\n\n`;
        content += `Accuracy: ${e.estimated_accuracy || 'N/A'}\nF1: ${e.estimated_f1 || 'N/A'}\n`;
        content += `Precision: ${e.estimated_precision || 'N/A'}\nRecall: ${e.estimated_recall || 'N/A'}\n`;
        content += `\nOverall Assessment:\n${e.overall_assessment || ''}\n`;
        content += `\nStrengths:\n${e.strengths || ''}\n`;
        content += `\nLimitations:\n${e.limitations || ''}\n`;
    } else if (selectedStage === "writer") {
        const r = state.report;
        content += `= RESEARCH REPORT =\n\nTitle: ${r.title || ''}\n`;
        const secs = ['abstract', 'introduction', 'literature_review', 'methodology', 'experiment_setup', 'results', 'discussion', 'conclusion', 'references'];
        secs.forEach(k => {
            if (r[k]) content += `\n== ${k.replace(/_/g, ' ').toUpperCase()} ==\n${r[k]}\n`;
        });
    }

    if (!content) { alert("No output to save for this agent."); return; }
    const blob = new Blob([content], { type: "text/plain" });
    downloadBlob(blob, `${name}_output_${Date.now()}.txt`);
}

// ── Save / Load / Export ─────────────────────────────────────
function saveProgress() {
    const nbData = nbCells.map(c => ({ id: c.id, title: c.title, code: c.code, output: c.output, error: c.error, images: c.images, time: c.time, status: c.status }));
    const data = { ...state, notebook_cells: nbData, saved_at: new Date().toISOString() };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    downloadBlob(blob, `research_progress_${Date.now()}.json`);
}

function loadProgress(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
        try {
            const data = JSON.parse(ev.target.result);
            // Restore state
            Object.keys(state).forEach(k => { if (data[k] !== undefined) state[k] = data[k]; });
            // Restore notebook
            if (data.notebook_cells) {
                nbCells = data.notebook_cells;
                cellCounter = nbCells.length;
                renderNotebook();
            }
            // Restore topic
            if (data.topic) $("#topic-input").value = data.topic;
            // Mark completed stages
            if (state.refined_topic) $(`#ind-planner`).className = "stage-indicator completed";
            if (state.papers.length) $(`#ind-paper_reader`).className = "stage-indicator completed";
            if (state.hypotheses.length) $(`#ind-hypothesis_gen`).className = "stage-indicator completed";
            if (state.experiment.cells?.length) $(`#ind-experiment`).className = "stage-indicator completed";
            if (state.evaluation.estimated_accuracy) $(`#ind-evaluation`).className = "stage-indicator completed";
            if (state.report.title) $(`#ind-writer`).className = "stage-indicator completed";

            selectStage("planner");
            alert("Progress loaded!");
        } catch (err) { alert("Invalid file: " + err.message); }
    };
    reader.readAsText(file);
    e.target.value = "";
}

async function exportDocx() {
    if (!state.report.title) { alert("No report available yet."); return; }
    try {
        const r = await fetch("/api/export/docx", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: state.report.title, sections: state.report }),
        });
        const blob = await r.blob();
        downloadBlob(blob, `report_${Date.now()}.docx`);
    } catch (e) { alert("Export failed: " + e.message); }
}

async function exportIpynb() {
    const cells = nbCells.map(c => ({ title: c.title, description: c.description || "", code: c.code }));
    if (!cells.length) { alert("No notebook cells to export."); return; }
    try {
        const r = await fetch("/api/export/ipynb", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cells, topic: state.topic || "Research" }),
        });
        const blob = await r.blob();
        downloadBlob(blob, `experiment_${Date.now()}.ipynb`);
    } catch (e) { alert("Export failed: " + e.message); }
}

function exportMarkdown() {
    const r = state.report;
    if (!r.title) { alert("No report available yet."); return; }
    let md = `# ${r.title}\n\n`;
    ['abstract', 'introduction', 'literature_review', 'methodology', 'experiment_setup', 'results', 'discussion', 'conclusion', 'references'].forEach(k => {
        if (r[k]) md += `## ${k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}\n\n${r[k]}\n\n`;
    });
    downloadBlob(new Blob([md], { type: "text/markdown" }), `report_${Date.now()}.md`);
}

function downloadBlob(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
}

// ── Timer ────────────────────────────────────────────────────
function startTimer() { seconds = 0; updateTimer(); timerInterval = setInterval(() => { seconds++; updateTimer(); }, 1000); }
function stopTimer() { clearInterval(timerInterval); }
function updateTimer() {
    const m = Math.floor(seconds / 60).toString().padStart(2, "0");
    const s = (seconds % 60).toString().padStart(2, "0");
    $("#pipeline-timer").textContent = `${m}:${s}`;
}

function finish(err = false) {
    isRunning = false; stopTimer();
    if (eventSource) { eventSource.close(); eventSource = null; }
    $("#start-btn").disabled = false;
    $(".btn-text").textContent = "Start";
    $("#topic-input").disabled = false;
}

// ── Utility ──────────────────────────────────────────────────
function esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}
