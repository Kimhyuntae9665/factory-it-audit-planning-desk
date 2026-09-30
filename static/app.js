"use strict";

const $ = id => document.getElementById(id);
const state = { actor: "planner_a", plan: null, generation: 0, sourceOpener: null,
  sourceGeneration: null, sourceRequestId: 0, loading: false };
const labels = {
  planning_candidate: "계획 자료 후보",
  outside_period: "기간 외 자료",
  wrong_artifact_type: "자료 종류 불일치",
  incomplete_artifact: "범위·필드 미완성",
  not_approved_draft: "미승인 초안",
  outside_audit_period: "감사 기간 외 판본"
};
const controls = {
  "ACCESS-01": "특권 계정 검토", "RESTORE-01": "복원 연습",
  "CHANGE-01": "변경 표본", "INVENTORY-01": "구성요소 목록"
};

function node(tag, className, value) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (value !== undefined) item.textContent = value;
  return item;
}
function status(message, bad = false) {
  $("notice").textContent = message;
  $("notice").style.borderColor = bad ? "#a33f32" : "#35659b";
  $("notice").style.background = bad ? "#fff0ed" : "#e4eefb";
}
function context() {
  return { service: $("service").value, period: $("period").value,
    cutoff: $("cutoff").value };
}
function query(ctx = context()) { return new URLSearchParams(ctx).toString(); }
async function api(path, opts = {}) {
  const response = await fetch(path, {
    ...opts, headers: { "X-Demo-Actor": state.actor, ...(opts.headers || {}) },
    cache: "no-store"
  });
  if (!response.ok) {
    let code = "http_" + response.status;
    try { code = (await response.json()).error || code; } catch (_) {}
    const error = new Error(code); error.status = response.status; throw error;
  }
  return response;
}
function setOptions(select, values, label) {
  select.replaceChildren();
  for (const value of values) {
    const option = node("option", "", label(value));
    option.value = value;
    select.append(option);
  }
}
function sourceButton(id, text) {
  const button = node("button", "source-button", text || id);
  button.type = "button";
  button.addEventListener("click", () => openSource(id, button));
  return button;
}
async function openSource(docId, opener) {
  const generation = state.generation;
  const requestId = ++state.sourceRequestId;
  state.sourceOpener = opener;
  state.sourceGeneration = generation;
  $("sourceTitle").textContent = "원문 · " + docId;
  $("sourceText").textContent = "";
  $("sourceStatus").textContent = "허용 범위와 자료 가용 시각 확인 중";
  if (!$("sourceDialog").open) $("sourceDialog").showModal();
  try {
    const response = await api("/api/source/" + encodeURIComponent(docId) + "?" + query());
    const data = await response.json();
    if (generation !== state.generation || requestId !== state.sourceRequestId ||
        !$("sourceDialog").open) return;
    $("sourceStatus").textContent = "원본 필드 · 출처 해시 · 자료 가용 시각";
    $("sourceText").textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    if (generation !== state.generation || requestId !== state.sourceRequestId ||
        !$("sourceDialog").open) return;
    $("sourceStatus").textContent = "원문 확인 실패: " + error.message;
    $("sourceText").textContent = "권한·가용 시각을 다시 확인해 주세요.";
  }
}
function addCell(row, label) {
  const td = node("td");
  td.dataset.label = label;
  row.append(td);
  return td;
}
function renderRows(plan) {
  const tbody = $("matrixBody");
  tbody.replaceChildren();
  for (const item of plan.rows) {
    const tr = node("tr");
    const idCell = addCell(tr, "통제");
    idCell.append(node("span", "control", item.control_id),
      node("span", "meta-line", controls[item.control_id] || ""));
    const policyCell = addCell(tr, "적용 정책");
    if (item.policy) {
      policyCell.append(sourceButton(item.policy.doc_id,
        item.policy.revision + " · " + item.policy.cadence + " · 승인 적용"));
      policyCell.append(node("span", "meta-line", item.policy.clause));
    } else {
      policyCell.append(node("span", "pill bad", "적용 정책 미확정"));
    }
    if (item.policy_alternatives.length) {
      const other = node("div", "alternative");
      for (const alt of item.policy_alternatives) {
        const line = node("div", "meta-line");
        line.append(sourceButton(alt.doc_id, alt.revision + " 원문"));
        line.append(" · " + labels[alt.exclusion] + " · " + alt.effective_from);
        other.append(line);
      }
      policyCell.append(other);
    }
    const evidenceCell = addCell(tr, "자료 후보");
    if (!item.candidates.length) evidenceCell.append(node("span", "meta-line", "현재 허용된 자료 후보 없음"));
    for (const candidate of item.candidates) {
      const box = node("div", "candidate");
      box.append(sourceButton(candidate.doc_id));
      const badge = node("span", "pill " +
        (candidate.planning_state === "planning_candidate" ? "good" : "warning"),
        labels[candidate.planning_state] || candidate.planning_state);
      box.append(badge);
      box.append(node("span", "meta-line",
        "기록일 " + candidate.event_date + " · 자료 가용 " +
        candidate.available_at.slice(0, 10) + " · 완전성 선언 " +
        candidate.completeness_declaration));
      if (candidate.missing_fields.length) {
        box.append(node("span", "meta-line", "누락 필드: " + candidate.missing_fields.join(", ")));
      }
      evidenceCell.append(box);
    }
    const resultCell = addCell(tr, "평가 결과");
    resultCell.append(node("span", "pill neutral", "미평가"));
    tbody.append(tr);
  }
}
function renderRequests(plan) {
  $("requestCount").textContent = String(plan.requests.length);
  const list = $("requestList");
  list.replaceChildren();
  if (!plan.requests.length) {
    list.append(node("li", "", "현재 계획상의 추가 자료 요청은 없습니다. 통제 효과는 여전히 미평가입니다."));
  }
  for (const request of plan.requests) {
    const li = node("li");
    li.append(node("strong", "", request.control_id || "자료 판본"));
    li.append(node("span", "", request.question));
    list.append(li);
  }
}
function renderHistory(rows) {
  const box = $("reviewHistory");
  box.replaceChildren();
  box.append(node("strong", "", "현재 범위의 검토 이력"));
  if (!rows.length) {
    box.append(node("p", "micro", "이 범위·자료 가용 기준에서 유효한 검토 기록이 없습니다."));
    return;
  }
  for (const receipt of rows) {
    const item = node("div", "history-item");
    const time = node("time", "", receipt.at.replace("T", " ").slice(0, 19) + " UTC");
    item.append(time, node("p", "", receipt.note));
    item.append(node("span", "meta-line",
      "계획 검토 기록 · 미해결 요청 " + receipt.open_request_count +
      "건 포함 · 효과성 미평가"));
    const button = node("button", "", "검토한 계획 JSON 받기");
    button.type = "button";
    button.addEventListener("click", () => exportReceipt(receipt.receipt_id, button));
    item.append(button);
    box.append(item);
  }
}
async function loadHistory(generation) {
  const response = await api("/api/reviews?" + query());
  const rows = await response.json();
  if (generation !== state.generation) return;
  renderHistory(rows);
}
function clearWorkspace() {
  state.plan = null;
  $("matrixBody").replaceChildren();
  $("requestList").replaceChildren();
  $("requestCount").textContent = "—";
  $("reviewHistory").replaceChildren();
  $("reviewButton").disabled = true;
  $("fingerprint").textContent = "";
}
async function loadPlan() {
  const generation = ++state.generation;
  $("reviewNote").value = "";
  if ($("sourceDialog").open) $("sourceDialog").close();
  clearWorkspace();
  $("planState").textContent = "자료 확인 중";
  status("선택한 범위의 승인 정책과 자료 가용 상태를 확인 중입니다.");
  try {
    const response = await api("/api/plan?" + query());
    const plan = await response.json();
    if (generation !== state.generation) return;
    state.plan = plan;
    renderRows(plan);
    renderRequests(plan);
    $("fingerprint").textContent = "계획 지문 " + plan.fingerprint.slice(0, 12);
    $("planState").textContent = plan.plan_status === "ready_for_planning_review"
      ? "계획 검토 가능" : "정책·자료 확인 보류";
    $("reviewButton").disabled = !($("actor").value === "planner_a" &&
      plan.plan_status === "ready_for_planning_review");
    status("선택한 자료 가용 기준의 매트릭스를 확인했습니다. 효과성은 미평가입니다.");
    await loadHistory(generation);
  } catch (error) {
    if (generation !== state.generation) return;
    clearWorkspace();
    $("planState").textContent = "확인 실패";
    status("자료 조회 실패: " + error.message, true);
  }
}
async function loadMeta(previousContext = null) {
  const generation = ++state.generation;
  $("reviewNote").value = "";
  clearWorkspace();
  if ($("sourceDialog").open) $("sourceDialog").close();
  status("역할별 허용 범위를 확인 중입니다.");
  try {
    const response = await api("/api/meta");
    const meta = await response.json();
    if (generation !== state.generation) return;
    $("siteLabel").textContent = meta.site + " · 데모 역할 · 외부 시스템 연결 없음";
    setOptions($("service"), meta.services, value => value);
    setOptions($("period"), meta.periods, value => value + "월");
    setOptions($("cutoff"), meta.cutoffs, value => value.slice(0, 16).replace("T", " ") + " UTC");
    if (previousContext) {
      for (const id of ["service", "period", "cutoff"]) {
        if ([...$(id).options].some(option => option.value === previousContext[id])) {
          $(id).value = previousContext[id];
        }
      }
    }
    await loadPlan();
  } catch (error) {
    if (generation !== state.generation) return;
    status("역할 범위 확인 실패: " + error.message, true);
  }
}
async function reviewPlan() {
  const plan = state.plan;
  if (!plan || state.loading) return;
  const note = $("reviewNote").value.trim();
  if (!note) { status("검토 메모를 입력해 주세요.", true); $("reviewNote").focus(); return; }
  const generation = state.generation;
  state.loading = true; $("reviewButton").disabled = true;
  try {
    const response = await api("/api/reviews", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ ...context(), fingerprint: plan.fingerprint, note })
    });
    await response.json();
    if (generation !== state.generation) return;
    status("이 범위의 계획 검토 기록을 저장했습니다. 통제 효과는 여전히 미평가입니다.");
    await loadHistory(generation);
  } catch (error) {
    if (generation !== state.generation) return;
    status("검토 기록 결과를 확인할 수 없습니다: " + error.message +
      ". 현재 범위 이력을 먼저 다시 확인하세요.", true);
    try { await loadHistory(generation); } catch (_) {}
  } finally {
    state.loading = false;
    if (generation === state.generation && state.plan &&
      state.plan.plan_status === "ready_for_planning_review") {
      $("reviewButton").disabled = state.actor !== "planner_a";
    }
  }
}
async function exportReceipt(id, button) {
  const generation = state.generation;
  button.disabled = true;
  try {
    const response = await api("/api/export/" + encodeURIComponent(id) + "?" + query());
    const text = await response.text();
    if (generation !== state.generation) return;
    const blob = new Blob([text], {type:"application/json"});
    const url = URL.createObjectURL(blob);
    const link = node("a"); link.href = url; link.download = "reviewed-audit-plan.json";
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status("현재 범위에 다시 맞춘 검토 계획 JSON을 받았습니다. 감사 결과 파일이 아닙니다.");
  } catch (error) {
    if (generation === state.generation) status("내보내기 실패: " + error.message, true);
  } finally { if (generation === state.generation) button.disabled = false; }
}

$("actor").addEventListener("change", () => {
  const previousContext = context();
  state.actor = $("actor").value;
  loadMeta(previousContext);
});
for (const id of ["service", "period", "cutoff"]) $(id).addEventListener("change", loadPlan);
$("reviewButton").addEventListener("click", reviewPlan);
$("sourceClose").addEventListener("click", () => $("sourceDialog").close());
$("sourceDialog").addEventListener("close", () => {
  ++state.sourceRequestId;
  if (state.sourceOpener && state.sourceOpener.isConnected &&
      state.sourceGeneration === state.generation) state.sourceOpener.focus();
  state.sourceOpener = null;
});
loadMeta();
