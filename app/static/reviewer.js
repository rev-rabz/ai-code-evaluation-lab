(() => {
  "use strict";

  const PAGE_SIZE = 20;
  let accessToken = null;
  let currentUser = null;
  let selectedEvaluationId = null;
  let queueItems = [];
  let reviewers = [];
  let pageOffset = 0;
  let totalItems = 0;

  const byId = (id) => document.getElementById(id);
  const loginView = byId("loginView");
  const dashboardView = byId("dashboardView");
  const loginMessage = byId("loginMessage");
  const dashboardMessage = byId("dashboardMessage");
  const queueList = byId("queueList");
  const detailContent = byId("detailContent");
  const emptyDetail = byId("emptyDetail");

  function showMessage(element, message, isError = true) {
    element.textContent = message || "";
    element.classList.toggle("success", !isError);
    element.classList.toggle("error", isError);
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium", timeStyle: "short"
    }).format(date);
  }

  function escapeLabel(value, fallback = "—") {
    return value === null || value === undefined || value === "" ? fallback : String(value);
  }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    const response = await fetch(path, { ...options, headers });
    let body = {};
    try { body = await response.json(); } catch { body = {}; }
    if (!response.ok) {
      const detail = typeof body.detail === "string" ? body.detail : `Request failed (${response.status}).`;
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function setSignedIn(user) {
    currentUser = user;
    loginView.hidden = true;
    dashboardView.hidden = false;
    byId("accountLabel").textContent = user.email;
    byId("accountLabel").hidden = false;
    byId("logoutButton").hidden = false;
    byId("assignmentSection").hidden = !user.is_admin;
    showMessage(loginMessage, "");
    refreshQueue();
  }

  function signOut() {
    accessToken = null;
    currentUser = null;
    selectedEvaluationId = null;
    queueItems = [];
    reviewers = [];
    pageOffset = 0;
    loginView.hidden = false;
    dashboardView.hidden = true;
    byId("accountLabel").hidden = true;
    byId("logoutButton").hidden = true;
    byId("passwordInput").value = "";
    byId("emailInput").focus();
    showMessage(loginMessage, "You have signed out.", false);
  }

  function createElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }

  function decisionTag(decision) {
    const value = decision || "pending";
    const label = value === "needs_changes" ? "Needs changes" : value.replaceAll("_", " ");
    return createElement("span", `status-pill status-${value}`, label);
  }

  function taskLabel(item) {
    return item.task_id || "Static analysis";
  }

  function renderQueue() {
    queueList.replaceChildren();
    if (!queueItems.length) {
      queueList.append(createElement("p", "muted small", "No submissions match this queue."));
    }
    for (const item of queueItems) {
      const button = createElement("button", `queue-item${item.id === selectedEvaluationId ? " selected" : ""}`);
      button.type = "button";
      button.addEventListener("click", () => selectEvaluation(item.id));

      const top = createElement("div", "queue-item-top");
      top.append(createElement("span", "queue-item-sub", `#${item.id} · ${escapeLabel(item.submitter?.email, "Legacy record")}`));
      top.append(decisionTag(item.human_review?.decision));
      const title = createElement("strong", "queue-item-title", taskLabel(item));
      const bottom = createElement("div", "queue-item-bottom");
      bottom.append(createElement("span", "queue-item-sub", `${Number(item.score).toFixed(0)}% · ${item.passed_tests}/${item.total_tests} tests`));
      bottom.append(createElement("span", "queue-item-sub", formatDate(item.created_at)));
      button.append(top, title, bottom);
      queueList.append(button);
    }

    const pending = queueItems.filter((item) => !item.human_review).length;
    const approved = queueItems.filter((item) => item.human_review?.decision === "approved").length;
    const attention = queueItems.filter((item) => ["needs_changes", "flagged"].includes(item.human_review?.decision)).length;
    byId("totalCount").textContent = String(totalItems);
    byId("pendingCount").textContent = String(pending);
    byId("approvedCount").textContent = String(approved);
    byId("attentionCount").textContent = String(attention);
    byId("queueSubtitle").textContent = `${totalItems} matching submission${totalItems === 1 ? "" : "s"}`;
    const first = totalItems ? pageOffset + 1 : 0;
    const last = Math.min(pageOffset + PAGE_SIZE, totalItems);
    byId("queueRange").textContent = `${first}–${last} of ${totalItems}`;
    byId("previousPage").disabled = pageOffset <= 0;
    byId("nextPage").disabled = pageOffset + PAGE_SIZE >= totalItems;
  }

  async function loadReviewers() {
    if (!currentUser?.is_admin) return;
    reviewers = await api("/api/v1/admin/reviewers");
    const select = byId("reviewerSelect");
    const selected = select.value;
    select.replaceChildren(new Option("Unassigned", ""));
    for (const reviewer of reviewers) {
      const role = reviewer.is_admin ? "admin" : "reviewer";
      select.append(new Option(`${reviewer.email} · ${role}`, String(reviewer.id)));
    }
    select.value = selected;
  }

  async function refreshQueue() {
    showMessage(dashboardMessage, "");
    byId("refreshButton").disabled = true;
    try {
      if (currentUser?.is_admin) await loadReviewers();
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(pageOffset) });
      const taskId = byId("taskFilter").value.trim();
      const status = byId("statusFilter").value;
      const decision = byId("decisionFilter").value;
      if (taskId) params.set("task_id", taskId);
      if (status) params.set("status", status);
      if (decision) params.set("decision", decision);
      const result = await api(`/api/v1/reviewer/evaluations?${params.toString()}`);
      queueItems = result.items || [];
      totalItems = result.total || 0;
      if (!queueItems.some((item) => item.id === selectedEvaluationId)) {
        selectedEvaluationId = queueItems[0]?.id ?? null;
      }
      renderQueue();
      if (selectedEvaluationId !== null) await loadDetail(selectedEvaluationId);
      else {
        detailContent.hidden = true;
        emptyDetail.hidden = false;
      }
    } catch (error) {
      showMessage(dashboardMessage, error.message);
      if (error.status === 401 || error.status === 403) signOut();
    } finally {
      byId("refreshButton").disabled = false;
    }
  }

  async function selectEvaluation(id) {
    selectedEvaluationId = id;
    renderQueue();
    await loadDetail(id);
  }

  function addTextBlock(parent, heading, value) {
    const section = createElement("section");
    section.append(createElement("h4", "", heading));
    const paragraph = createElement("p", "", value);
    section.append(paragraph);
    parent.append(section);
  }

  function renderAIReview(review) {
    const target = byId("aiReviewContent");
    target.replaceChildren();
    if (!review) {
      target.append(createElement("p", "muted", "No AI review attached to this submission."));
      byId("aiModel").textContent = "";
      return;
    }
    byId("aiModel").textContent = review.model || "";
    addTextBlock(target, "Summary", review.review?.summary || "");
    const strengths = review.review?.strengths || [];
    if (strengths.length) {
      const section = createElement("section");
      section.append(createElement("h4", "", "Strengths"));
      const list = createElement("ul");
      for (const value of strengths) list.append(createElement("li", "", value));
      section.append(list);
      target.append(section);
    }
    const findings = review.review?.findings || [];
    if (findings.length) {
      const section = createElement("section");
      section.append(createElement("h4", "", "AI findings"));
      for (const finding of findings) {
        const p = createElement("p", "", `${finding.severity || "finding"} · ${finding.title || ""}: ${finding.explanation || ""}`);
        section.append(p);
      }
      target.append(section);
    }
    const nextSteps = review.review?.next_steps || [];
    if (nextSteps.length) {
      const section = createElement("section");
      section.append(createElement("h4", "", "Suggested next steps"));
      const list = createElement("ul");
      for (const value of nextSteps) list.append(createElement("li", "", value));
      section.append(list);
      target.append(section);
    }
  }

  async function loadDetail(id) {
    try {
      showMessage(dashboardMessage, "");
      const detail = await api(`/api/v1/reviewer/evaluations/${id}`);
      emptyDetail.hidden = true;
      detailContent.hidden = false;
      byId("detailId").textContent = `#${detail.id}`;
      byId("detailTitle").textContent = detail.task?.title || detail.task?.task_id || "Static analysis submission";
      byId("detailMeta").textContent = `${detail.submitter?.email || "Legacy record"} · ${detail.language} · ${formatDate(detail.created_at)}`;
      byId("scoreBadge").textContent = `${Number(detail.score).toFixed(0)}%`;
      byId("detailStatus").textContent = detail.status;
      byId("detailTests").textContent = `${detail.passed_tests}/${detail.total_tests}`;
      byId("detailRuntime").textContent = detail.execution_timed_out ? "Timed out" : (detail.execution_performed ? (detail.execution_duration_ms == null ? "Executed" : `${Number(detail.execution_duration_ms).toFixed(0)} ms`) : "Not run");
      byId("languageLabel").textContent = detail.language;
      byId("sourceCode").textContent = detail.source_code || "";
      renderTestResults(detail.result?.test_feedback || []);
      renderFindings(detail.result?.findings || []);
      renderAIReview(detail.ai_review);
      renderHumanReview(detail.human_review);
      if (currentUser?.is_admin) {
        const currentAssignment = detail.assignment?.reviewer_id ? String(detail.assignment.reviewer_id) : "";
        byId("reviewerSelect").value = currentAssignment;
        showMessage(byId("assignmentMessage"), currentAssignment ? `Assigned to ${detail.assignment.reviewer_id}.` : "This submission is currently unassigned.", false);
      }
    } catch (error) {
      showMessage(dashboardMessage, error.message);
      if (error.status === 401 || error.status === 403) signOut();
    }
  }

  function renderTestResults(cases) {
    const target = byId("testResults");
    target.replaceChildren();
    if (!cases.length) {
      target.append(createElement("p", "muted small", "No trusted test results are available."));
      return;
    }
    for (const item of cases) {
      const row = createElement("div", "result-row");
      row.append(createElement("span", "", item.name || "Test case"));
      row.append(createElement("strong", item.passed ? "result-pass" : "result-fail", item.passed ? "PASSED" : "FAILED"));
      target.append(row);
    }
  }

  function renderFindings(findings) {
    const target = byId("staticFindings");
    target.replaceChildren();
    if (!findings.length) {
      target.append(createElement("p", "muted small", "No static-analysis findings recorded."));
      return;
    }
    for (const finding of findings) {
      const row = createElement("div", "finding-row");
      row.append(createElement("strong", "", `${finding.severity || "Finding"} · ${finding.title || finding.code || "Code analysis"}`));
      row.append(createElement("p", "", finding.message || finding.description || finding.explanation || ""));
      target.append(row);
    }
  }

  function renderHumanReview(review) {
    byId("humanReviewState").replaceChildren();
    byId("humanReviewState").append(decisionTag(review?.decision));
    if (review) {
      byId("decisionSelect").value = review.decision;
      byId("reviewNotes").value = review.notes || "";
      showMessage(byId("reviewMessage"), `Last updated ${formatDate(review.updated_at)} · ${review.reviewer_email || "Reviewer"}`, false);
    } else {
      byId("decisionSelect").value = "approved";
      byId("reviewNotes").value = "";
      showMessage(byId("reviewMessage"), "No human review has been saved yet.", false);
    }
  }

  byId("loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    showMessage(loginMessage, "Signing in…", false);
    const button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const result = await api("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: byId("emailInput").value.trim(),
          password: byId("passwordInput").value
        })
      });
      accessToken = result.access_token;
      const user = result.user || await api("/api/v1/auth/me");
      if (!user.is_admin && !user.is_reviewer) {
        accessToken = null;
        throw new Error("This account does not have reviewer or administrator access.");
      }
      setSignedIn(user);
    } catch (error) {
      showMessage(loginMessage, error.message);
    } finally {
      button.disabled = false;
    }
  });

  byId("logoutButton").addEventListener("click", signOut);
  byId("refreshButton").addEventListener("click", refreshQueue);
  byId("filterForm").addEventListener("submit", (event) => {
    event.preventDefault();
    pageOffset = 0;
    selectedEvaluationId = null;
    refreshQueue();
  });
  byId("previousPage").addEventListener("click", () => {
    pageOffset = Math.max(0, pageOffset - PAGE_SIZE);
    selectedEvaluationId = null;
    refreshQueue();
  });
  byId("nextPage").addEventListener("click", () => {
    if (pageOffset + PAGE_SIZE < totalItems) {
      pageOffset += PAGE_SIZE;
      selectedEvaluationId = null;
      refreshQueue();
    }
  });

  byId("saveAssignmentButton").addEventListener("click", async () => {
    if (selectedEvaluationId === null) return;
    const reviewerId = byId("reviewerSelect").value;
    const button = byId("saveAssignmentButton");
    button.disabled = true;
    try {
      await api(`/api/v1/admin/evaluations/${selectedEvaluationId}/assignment`, {
        method: "PUT",
        body: JSON.stringify({ reviewer_id: reviewerId ? Number(reviewerId) : null })
      });
      showMessage(byId("assignmentMessage"), "Assignment saved.", false);
      await refreshQueue();
    } catch (error) {
      showMessage(byId("assignmentMessage"), error.message);
    } finally {
      button.disabled = false;
    }
  });

  byId("reviewForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (selectedEvaluationId === null) return;
    const button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      await api(`/api/v1/reviewer/evaluations/${selectedEvaluationId}/review`, {
        method: "PUT",
        body: JSON.stringify({
          decision: byId("decisionSelect").value,
          notes: byId("reviewNotes").value
        })
      });
      showMessage(byId("reviewMessage"), "Human review saved.", false);
      await refreshQueue();
    } catch (error) {
      showMessage(byId("reviewMessage"), error.message);
    } finally {
      button.disabled = false;
    }
  });
})();
