const state = {
    activeWorkflowId: null,
    pollTimer: null,
};

const samples = {
    sales: {
        sender: "buyer@example.com",
        subject: "Requesting enterprise pricing",
        body: "Hello, can I get an enterprise quote for 500 seats?",
    },
    technical: {
        sender: "dev@example.com",
        subject: "The dashboard crashes",
        body: "The dashboard crashes whenever I export a CSV. Please help.",
    },
    billing: {
        sender: "finance@example.com",
        subject: "Refund for incorrect invoice",
        body: "We were charged twice for invoice 8841. Please issue a refund.",
    },
    account: {
        sender: "customer@example.com",
        subject: "Cannot access my account after changing my phone",
        body: "Hi, I changed my mobile phone yesterday and now the verification code is going to my old number. I cannot log in. Can someone update the number for me?",
    },
    spam: {
        sender: "scam@example.com",
        subject: "You won a prize!",
        body: "Click here to claim your password reward!",
    },
    general: {
        sender: "curious@example.com",
        subject: "Weekend support hours",
        body: "What are your weekend support hours?",
    },
};

// Ordered pipeline stages. Keys match the `data-node` attributes in index.html.
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
    response_agent: "response",
    reviewer_agent: "review",
    human_pause: "approval",
    finalize: "final",
    finalize_rejected: "final",
};

function stageFor(agentName) {
    if (!agentName) return null;
    if (AGENT_STAGE[agentName]) return AGENT_STAGE[agentName];
    // Specialist agents are named "<specialist>_agent" (e.g. account_access_agent).
    if (agentName.endsWith("_agent")) return "specialist";
    return null;
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

function attachSampleButtons(form) {
    document.querySelectorAll("[data-sample]").forEach((button) => {
        button.addEventListener("click", () => {
            const sample = samples[button.dataset.sample];
            if (!sample) return;
            form.sender.value = sample.sender;
            form.subject.value = sample.subject;
            form.body.value = sample.body;
        });
    });
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

    STAGES.forEach((key) => {
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
            STAGES.find((k) => k !== "approval" && k !== "final" && !reached.has(k)) ||
            STAGES.find((k) => !reached.has(k));
        if (next) {
            const el = qs(`[data-node="${next}"]`);
            if (el && !el.classList.contains("completed")) el.classList.add("active");
        }
    }
    if (status === "error") {
        const failed = STAGES.find((k) => !reached.has(k));
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

    setContent("classification", classification && formatClassification(classification));
    setContent(
        "supervisor",
        s.selected_specialist ? `Routed to: ${s.selected_specialist}` : null
    );
    setContent("specialist", specialist && formatSpecialist(specialist));
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
        s.recommended_action ? `\nAction: ${s.recommended_action}` : "",
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
        loadHistory();
    }
}

function startPolling(workflowId) {
    stopPolling();
    state.activeWorkflowId = workflowId;
    pollTick(workflowId);
    state.pollTimer = setInterval(() => pollTick(workflowId), 900);
}

/* ---------- History ---------- */

async function loadHistory(panelSelector = "#history-list") {
    const container = qs(panelSelector);
    if (!container) return;
    const response = await fetch("/api/workflows");
    const data = await response.json();
    if (container.tagName === "TBODY") {
        container.innerHTML = data
            .map(
                (item) => `
                <tr>
                    <td>${item.id}</td>
                    <td>${escapeHtml(item.subject)}</td>
                    <td>${item.category || "—"}</td>
                    <td><span class="status-badge ${statusClass(item.status)}">${prettyStatus(item.status)}</span></td>
                    <td>${new Date(item.updated_at).toLocaleString()}</td>
                    <td><a href="/workflows/${item.id}">View</a></td>
                </tr>`
            )
            .join("");
    } else {
        container.innerHTML = data
            .slice(0, 8)
            .map(
                (item) => `
                <button class="history-card" data-open="${item.id}">
                    <p><strong>${escapeHtml(item.subject)}</strong></p>
                    <div class="history-meta">
                        <span>${item.category || "Unclassified"}</span>
                        <span class="status-badge ${statusClass(item.status)}">${prettyStatus(item.status)}</span>
                    </div>
                </button>`
            )
            .join("");
        container.querySelectorAll("[data-open]").forEach((btn) => {
            btn.addEventListener("click", () => startPolling(btn.dataset.open));
        });
    }
}

/* ---------- Page initializers ---------- */

function initDashboard() {
    const form = document.getElementById("email-form");
    attachSampleButtons(form);
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const payload = {
            sender: form.sender.value,
            subject: form.subject.value,
            body: form.body.value,
        };
        resetCards();
        setRunStatus("processing");
        try {
            const result = await postJSON("/api/emails/analyze", payload);
            startPolling(result.workflow_id);
            loadHistory();
        } catch (error) {
            setRunStatus("error", { approval_reason: error.message });
            alert(error.message);
        }
    });
    loadHistory();
    wireApprovalButtons();

    // Deep-link support: /?wf=<id> reopens an existing run.
    const params = new URLSearchParams(window.location.search);
    const wf = params.get("wf");
    if (wf) startPolling(wf);
}

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

function initArchitecture() {
    if (window.mermaid) {
        window.mermaid.initialize({ startOnLoad: true, theme: "dark" });
    }
}

window.addEventListener("DOMContentLoaded", () => {
    const page = document.body.dataset.page;
    if (page === "dashboard") initDashboard();
    if (page === "history") initHistory();
    if (page === "workflow") initWorkflowPage();
    if (page === "architecture") initArchitecture();
});
