const state = {
    activeWorkflowId: null,
    pollTimer: null,
};

// Ordered pipeline stages for the multi-agentic mode's stepper.
const STAGES = [
    "intake",
    "classify",
    "supervisor",
    "specialist",
    "response",
    "review",
    "approval",
    "final",
];

const STAGE_LABELS = {
    intake: "Intake",
    classify: "Classification",
    supervisor: "Supervisor",
    specialist: "Specialist",
    response: "Draft Response",
    review: "Reviewer",
    approval: "Human Approval",
    final: "Finalize",
};

// Map a persisted trace agent_name to a pipeline stage.
const AGENT_STAGE = {
    intake: "intake",
    classification_agent: "classify",
    supervisor_agent: "supervisor",
    route_agent: "route",
    response_agent: "response",
    reviewer_agent: "review",
    human_pause: "approval",
    finalize: "final",
    finalize_rejected: "final",
};

function stageFor(agentName) {
    if (!agentName) return null;
    if (AGENT_STAGE[agentName]) return AGENT_STAGE[agentName];
    // Department agents are named "<department>_agent" (e.g. account_access_agent).
    if (agentName.endsWith("_agent")) return "specialist";
    return null;
}

// Two pipelines share one stepper component: the naive agentic baseline
// (classify -> forward, nothing else) and the full multi-agentic chain.
const STAGE_SETS = {
    agentic: ["intake", "classify", "route", "final"],
    multi_agentic: STAGES,
};
STAGE_LABELS.route = "Route & Forward";

let ACTIVE_STAGES = STAGES;

function renderStepperGrid(container, stages) {
    if (!container) return;
    container.innerHTML = stages
        .map(
            (key, i) =>
                `<div class="node" data-node="${key}"><span class="node-index">${i + 1}</span>${STAGE_LABELS[key]}</div>`
        )
        .join("");
}

const TERMINAL_STATUSES = new Set(["completed", "rejected", "error", "pending_approval"]);

function qs(selector) {
    return document.querySelector(selector);
}

async function postJSON(url, payload) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || "Request failed");
    }
    return response.json();
}

async function fetchDetail(workflowId) {
    const response = await fetch(`/api/workflows/${workflowId}`);
    if (!response.ok) throw new Error("Workflow not found");
    return response.json();
}

function resetCards() {
    document.querySelectorAll("[data-content]").forEach((el) => {
        el.textContent = "Awaiting…";
    });
    const status = qs("#approval-status");
    if (status) {
        status.textContent = "—";
        status.className = "status-badge large";
    }
    document.querySelectorAll("[data-node]").forEach((el) => {
        el.classList.remove("completed", "active", "error", "rejected");
    });
    toggleApprovalPanel(false);
    const trace = qs("#trace-list");
    if (trace) trace.innerHTML = "";
}

/* ---------- Run status banner ---------- */

const RUN_STATUS = {
    processing: { label: "Running agents…", cls: "running", spin: true },
    pending_approval: { label: "Paused — human approval required", cls: "warn", spin: false },
    completed: { label: "Completed", cls: "ok", spin: false },
    rejected: { label: "Rejected", cls: "danger", spin: false },
    error: { label: "Failed", cls: "danger", spin: false },
    created: { label: "Queued…", cls: "running", spin: true },
};

function setRunStatus(status, detail) {
    const banner = qs("#run-status");
    if (!banner) return;
    const meta = RUN_STATUS[status] || { label: status || "Idle", cls: "", spin: false };
    banner.className = `run-status ${meta.cls}`;
    banner.hidden = false;
    const spinner = meta.spin ? '<span class="spinner"></span>' : "";
    let extra = "";
    if (status === "error" && detail && detail.approval_reason) {
        extra = ` — ${detail.approval_reason}`;
    }
    banner.innerHTML = `${spinner}<span>${meta.label}${extra}</span>`;
}

/* ---------- Stepper ---------- */

function renderStepper(trace, status) {
    const reached = new Set((trace || []).map((t) => stageFor(t.agent_name)).filter(Boolean));

    ACTIVE_STAGES.forEach((key) => {
        const el = qs(`[data-node="${key}"]`);
        if (!el) return;
        el.classList.remove("completed", "active", "error", "rejected");

        let cls = "";
        if (status === "completed") {
            cls = "completed";
        } else if (status === "rejected") {
            cls = key === "final" ? "rejected" : "completed";
        } else if (status === "pending_approval") {
            if (key === "approval") cls = "active";
            else if (key === "final") cls = "";
            else cls = reached.has(key) ? "completed" : "";
        } else {
            // processing / created / error
            if (reached.has(key)) cls = "completed";
        }
        if (cls) el.classList.add(cls);
    });

    // While running, highlight the next stage that hasn't reported yet.
    if (status === "processing" || status === "created") {
        const next =
            ACTIVE_STAGES.find((k) => k !== "approval" && k !== "final" && !reached.has(k)) ||
            ACTIVE_STAGES.find((k) => !reached.has(k));
        if (next) {
            const el = qs(`[data-node="${next}"]`);
            if (el && !el.classList.contains("completed")) el.classList.add("active");
        }
    }
    if (status === "error") {
        const failed = ACTIVE_STAGES.find((k) => !reached.has(k));
        if (failed) {
            const el = qs(`[data-node="${failed}"]`);
            if (el) el.classList.add("error");
        }
    }
}

/* ---------- Trace feed ---------- */

function renderTrace(items) {
    const container = qs("#trace-list");
    if (!container) return;
    if (!items || !items.length) {
        container.innerHTML = '<p class="trace-empty">No activity yet.</p>';
        return;
    }
    container.innerHTML = items
        .map((item) => {
            const stage = stageFor(item.agent_name);
            const title = stage ? STAGE_LABELS[stage] : item.agent_name;
            const statusCls = item.status === "error" ? "err" : item.status === "pending" ? "warn" : "ok";
            const summary = item.output_summary ? `<p class="trace-summary">${escapeHtml(item.output_summary)}</p>` : "";
            const dur = typeof item.duration_ms === "number" ? `${item.duration_ms}ms` : "";
            return `
                <div class="trace-item ${statusCls}">
                    <div class="trace-dot"></div>
                    <div class="trace-body">
                        <div class="trace-top">
                            <span class="trace-name">${escapeHtml(title)}</span>
                            <span class="trace-meta">${item.status} · ${dur}</span>
                        </div>
                        ${summary}
                    </div>
                </div>`;
        })
        .join("");
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

/* ---------- Result cards ---------- */

function renderCards(detail) {
    if (!detail) return;
    const s = detail.state_json || {};
    const classification = s.classification;
    const specialist = s.specialist_result;
    const draft = detail.status === "completed" ? detail.final_response || s.final_response || s.draft_response : s.draft_response;
    const review = s.review_result;
    const isAgentic = detail.mode === "agentic";

    setContent("classification", classification && formatClassification(classification));
    if (isAgentic) {
        setContent("supervisor", s.routed_to ? `Forwarded to: ${s.routed_to}\n(No supervisor step — agentic mode routes directly.)` : null);
        if (detail.status === "completed") setContent("specialist", "Not applicable — agentic mode has no department agent or decision step.");
    } else {
        setContent("supervisor", s.selected_specialist ? `Routed to: ${s.selected_specialist}` : null);
        setContent("specialist", specialist && formatSpecialist(specialist));
    }
    setContent("draft", draft && `${draft.subject || ""}\n\n${draft.body || ""}`.trim());
    setContent("review", review && formatReview(review));

    const approvalEl = qs("#approval-status");
    if (approvalEl) {
        approvalEl.textContent = prettyStatus(detail.status);
        approvalEl.className = `status-badge large ${statusClass(detail.status)}`;
    }
}

function setContent(key, value) {
    const el = qs(`[data-content="${key}"]`);
    if (!el) return;
    if (value) el.textContent = value;
}

function formatClassification(c) {
    const conf = typeof c.confidence === "number" ? ` · ${(c.confidence * 100).toFixed(0)}% conf` : "";
    return [
        `Category : ${c.category}`,
        `Priority : ${c.priority}${conf}`,
        c.summary ? `\n${c.summary}` : "",
    ].join("\n");
}

function formatSpecialist(s) {
    return [
        `Risk: ${s.risk}`,
        s.analysis ? `\n${s.analysis}` : "",
        s.action ? `\nDecision: ${s.action}` : "",
        s.action_detail ? s.action_detail : "",
    ].join("\n");
}

function formatReview(r) {
    return [
        `Decision : ${r.decision}`,
        `Grounded : ${r.grounded}   Tone OK: ${r.tone_ok}`,
        r.feedback ? `\n${r.feedback}` : "",
    ].join("\n");
}

function prettyStatus(status) {
    return (RUN_STATUS[status] && RUN_STATUS[status].label) || status || "—";
}

function statusClass(status) {
    if (status === "completed") return "ok";
    if (status === "rejected" || status === "error") return "danger";
    if (status === "pending_approval") return "warn";
    return "";
}

/* ---------- Approval panel ---------- */

function toggleApprovalPanel(show, detail) {
    const panel = qs("#approval-panel");
    if (!panel) return;
    if (!show) {
        panel.hidden = true;
        return;
    }
    panel.hidden = false;
    qs("#approval-reason").textContent = detail.approval_reason || "Approval required";
    const draft = (detail.state_json && detail.state_json.draft_response) || {};
    const subject = draft.subject || "";
    const body = draft.body || "";
    qs("#approval-draft").value = `${subject}\n\n${body}`.trim();
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function wireApprovalButtons() {
    const approveBtn = qs("#approve-btn");
    const rejectBtn = qs("#reject-btn");

    if (approveBtn) {
        approveBtn.addEventListener("click", async () => {
            if (!state.activeWorkflowId) return;
            const raw = qs("#approval-draft").value;
            const [subject, ...bodyParts] = raw.split("\n\n");
            const body = bodyParts.join("\n\n").trim();
            setButtonsBusy(true);
            try {
                await postJSON(`/api/reviews/${state.activeWorkflowId}/approve`, {
                    edited_response: {
                        subject: (subject || "Re: Customer request").trim(),
                        body: body || raw.trim(),
                    },
                });
                toggleApprovalPanel(false);
                startPolling(state.activeWorkflowId);
            } catch (error) {
                alert(error.message);
            } finally {
                setButtonsBusy(false);
            }
        });
    }

    if (rejectBtn) {
        rejectBtn.addEventListener("click", async () => {
            if (!state.activeWorkflowId) return;
            const reason = prompt("Provide a rejection reason", "Requires manual follow-up");
            if (!reason) return;
            setButtonsBusy(true);
            try {
                await postJSON(`/api/reviews/${state.activeWorkflowId}/reject`, { reason });
                toggleApprovalPanel(false);
                startPolling(state.activeWorkflowId);
            } catch (error) {
                alert(error.message);
            } finally {
                setButtonsBusy(false);
            }
        });
    }
}

function setButtonsBusy(busy) {
    ["#approve-btn", "#reject-btn"].forEach((sel) => {
        const btn = qs(sel);
        if (btn) btn.disabled = busy;
    });
}

/* ---------- Polling ---------- */

function stopPolling() {
    if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
    }
}

async function pollTick(workflowId) {
    let detail;
    try {
        detail = await fetchDetail(workflowId);
    } catch (error) {
        return; // transient; try again next tick
    }
    state.activeWorkflowId = workflowId;
    renderCards(detail);
    renderTrace(detail.trace || []);
    renderStepper(detail.trace || [], detail.status);
    setRunStatus(detail.status, detail);

    if (TERMINAL_STATUSES.has(detail.status)) {
        stopPolling();
        toggleApprovalPanel(detail.status === "pending_approval", detail);
    }
}

function startPolling(workflowId) {
    stopPolling();
    state.activeWorkflowId = workflowId;
    pollTick(workflowId);
    state.pollTimer = setInterval(() => pollTick(workflowId), 900);
}

/* ---------- History ---------- */

async function loadHistory(panelSelector = "#history-table tbody") {
    const container = qs(panelSelector);
    if (!container) return;
    const response = await fetch("/api/workflows");
    const data = await response.json();
    container.innerHTML = data
        .map(
            (item) => `
            <tr>
                <td>${item.id}</td>
                <td>${escapeHtml(item.subject)}</td>
                <td>${item.category || "—"}</td>
                <td>${item.mode || "—"}</td>
                <td><span class="status-badge ${statusClass(item.status)}">${prettyStatus(item.status)}</span></td>
                <td>${new Date(item.updated_at).toLocaleString()}</td>
                <td><a href="/workflows/${item.id}">View</a></td>
            </tr>`
        )
        .join("");
}

/* ---------- Page initializers ---------- */

function initHistory() {
    loadHistory("#history-table tbody");
}

async function initWorkflowPage() {
    const workflowId = document.body.dataset.workflowId;
    if (!workflowId) return;
    const detail = await fetchDetail(workflowId);
    state.activeWorkflowId = workflowId;
    renderCards(detail);
    renderTrace(detail.trace || []);
    renderStepper(detail.trace || [], detail.status);
    setRunStatus(detail.status, detail);
    toggleApprovalPanel(detail.status === "pending_approval", detail);
    wireApprovalButtons();

    const detailContainer = qs("#workflow-detail");
    if (detailContainer) {
        detailContainer.innerHTML = `<h2>Raw State</h2><pre>${escapeHtml(JSON.stringify(detail.state_json, null, 2))}</pre>`;
    }
}

/* ---------- Inbox page (agentic vs multi-agentic demo) ---------- */

const inboxState = {
    mode: "agentic",
    emails: [],
    selected: null,
};

function renderInboxList() {
    const container = qs("#inbox-list");
    if (!container) return;
    container.innerHTML = inboxState.emails
        .map(
            (email) => `
            <button class="inbox-item ${inboxState.selected && inboxState.selected.id === email.id ? "selected" : ""}" data-email-id="${email.id}">
                <div class="inbox-item-top">
                    <span>${escapeHtml(email.sender)}</span>
                </div>
                <span class="inbox-item-subject">${escapeHtml(email.subject)}</span>
                <span class="inbox-item-preview">${escapeHtml(email.body)}</span>
            </button>`
        )
        .join("");
    container.querySelectorAll("[data-email-id]").forEach((btn) => {
        btn.addEventListener("click", () => selectEmail(btn.dataset.emailId));
    });
}

function selectEmail(id) {
    const email = inboxState.emails.find((e) => e.id === id);
    if (!email) return;
    inboxState.selected = email;
    renderInboxList();
    qs("#reading-empty").hidden = true;
    qs("#reading-content").hidden = false;
    qs("#reading-subject").textContent = email.subject;
    qs("#reading-sender").textContent = email.sender;
    qs("#reading-body").textContent = email.body;
    resetCards();
    qs("#run-status").hidden = true;
}

function setMode(mode) {
    inboxState.mode = mode;
    ACTIVE_STAGES = STAGE_SETS[mode];
    document.querySelectorAll(".mode-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.mode === mode);
    });
    renderStepperGrid(qs("#workflow-grid"), ACTIVE_STAGES);
    resetCards();
}

function wireModeToggle() {
    document.querySelectorAll(".mode-btn").forEach((btn) => {
        btn.addEventListener("click", () => setMode(btn.dataset.mode));
    });
}

function wireComposeModal() {
    const modal = qs("#compose-modal");
    const openBtn = qs("#compose-btn");
    const closeBtn = qs("#compose-close");
    const form = qs("#compose-form");
    if (!modal || !openBtn) return;

    openBtn.addEventListener("click", () => {
        modal.hidden = false;
    });
    closeBtn.addEventListener("click", () => {
        modal.hidden = true;
    });
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const email = {
            id: `custom-${Date.now()}`,
            sender: form.sender.value,
            subject: form.subject.value,
            body: form.body.value,
        };
        inboxState.emails.unshift(email);
        modal.hidden = true;
        form.reset();
        renderInboxList();
        selectEmail(email.id);
    });
}

function wireRunButton() {
    const runBtn = qs("#run-btn");
    if (!runBtn) return;
    runBtn.addEventListener("click", async () => {
        if (!inboxState.selected) return;
        resetCards();
        const statusBanner = qs("#run-status");
        statusBanner.hidden = false;
        setRunStatus("processing");
        try {
            const result = await postJSON("/api/emails/analyze", {
                sender: inboxState.selected.sender,
                subject: inboxState.selected.subject,
                body: inboxState.selected.body,
                mode: inboxState.mode,
            });
            startPolling(result.workflow_id);
        } catch (error) {
            setRunStatus("error", { approval_reason: error.message });
        }
    });
}

async function initInbox() {
    setMode("agentic");
    wireModeToggle();
    wireComposeModal();
    wireRunButton();
    wireApprovalButtons();

    try {
        const response = await fetch("/static/seed_inbox.json");
        inboxState.emails = await response.json();
    } catch (error) {
        inboxState.emails = [];
    }
    renderInboxList();
}

window.addEventListener("DOMContentLoaded", () => {
    const page = document.body.dataset.page;
    if (page === "history") initHistory();
    if (page === "workflow") initWorkflowPage();
    if (page === "inbox") initInbox();
});
