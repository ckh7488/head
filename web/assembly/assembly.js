import { WalkthroughScene } from "./scene.js";
import { hardware, steps } from "./steps.js";

const el = id => document.getElementById(id);
const choose = id => steps.findIndex(step => step.id === id);
const fmt = value => new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 }).format(value);
const mm = value => `${fmt(value)} mm`;
const state = {
  index: 0, position: 0, ghost: false, section: false, issues: false,
};
let scene, stops, animation;
const needsCheck = step => Boolean(step.blocker || step.hold);

function makeIndex() {
  const list = el("step-list");
  list.replaceChildren();
  const select = el("step-select");
  select.replaceChildren();
  const groups = new Map();
  for (const [index, step] of steps.entries()) {
    if (state.issues && !needsCheck(step)) continue;
    if (!groups.has(step.group)) {
      const group = document.createElement("section");
      group.className = "step-group";
      const heading = document.createElement("h3");
      heading.textContent = step.group;
      const ordered = document.createElement("ol");
      group.append(heading, ordered);
      list.append(group);
      const options = document.createElement("optgroup");
      options.label = step.group;
      select.append(options);
      groups.set(step.group, { ordered, options });
    }
    const { ordered, options } = groups.get(step.group);
    const row = document.createElement("li");
    const button = document.createElement("button");
    button.className = "step-button";
    button.dataset.step = step.id;
    if (step.blocker) button.setAttribute("aria-label", `${index + 1}. ${step.title} · CAD 간섭`);
    const ordinal = document.createElement("span");
    ordinal.className = "ordinal";
    ordinal.textContent = String(index + 1).padStart(2, "0");
    const name = document.createElement("span");
    name.textContent = step.title;
    button.append(ordinal, name);
    if (step.blocker) {
      const marker = document.createElement("i");
      marker.className = "point";
      marker.setAttribute("aria-hidden", "true");
      button.append(marker);
    }
    row.append(button);
    ordered.append(row);
    const option = new Option(`${index + 1}. ${step.title}${step.blocker ? " · 간섭" : ""}`, step.id);
    options.append(option);
  }
}

const current = () => steps[state.index];
const span = () => Math.hypot(...current().moves[0].offset);
const stopData = () => stops?.[current().id];
const limit = () => stopData() ? 1 - stopData().remaining / span() : 1;
const candidates = () => steps.map((step, index) => ({step, index})).filter(({step}) => !state.issues || needsCheck(step));
const stepButton = () => el("step-list").querySelector(`[data-step="${current().id}"]`);

function updateNavigation() {
  const index = candidates().findIndex(item => item.index === state.index);
  const choices = candidates();
  el("prev").disabled = index <= 0;
  el("next").disabled = index === -1 || index >= choices.length - 1;
  for (const button of el("step-list").querySelectorAll("[data-step]")) {
    if (button.dataset.step === current().id) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  }
  el("step-select").value = current().id;
  const selected = stepButton();
  const list = el("step-list");
  if (selected && list.clientHeight) {
    const area = list.getBoundingClientRect();
    const rect = selected.getBoundingClientRect();
    if (rect.top < area.top) list.scrollTop -= area.top - rect.top + 8;
    else if (rect.bottom > area.bottom) list.scrollTop += rect.bottom - area.bottom + 8;
  }
}

function position(value) {
  state.position = Math.max(0, Math.min(1, value));
  const remain = (1 - state.position) * span();
  const stop = stopData();
  const hit = Boolean(stop && Math.abs(remain - stop.remaining) < .09);
  const target = Boolean(stop && remain < .05);
  el("position").value = Math.round(state.position * 1000);
  el("position").setAttribute("aria-valuetext", `목표까지 ${mm(remain)}`);
  el("distance").textContent = `목표까지 ${mm(remain)}`;
  el("stage-tag").hidden = !(hit || target);
  el("stage-tag").textContent = hit ? "CAD 간섭 위치" : "목표 형상 · 장착 경로 필요";
  el("hit-legend").hidden = !hit;
  scene?.setPosition(state.position, hit);
}

function pause() {
  if (animation) cancelAnimationFrame(animation);
  animation = null;
  el("play").textContent = "재생";
  el("play").setAttribute("aria-pressed", "false");
}

function applyView() {
  el("ghost").setAttribute("aria-pressed", String(state.ghost));
  el("section").setAttribute("aria-pressed", String(state.section));
  scene?.applyStyle(state);
}

function details() {
  const step = current();
  const stop = stopData();
  const status = el("detail-status");
  status.dataset.kind = needsCheck(step) ? "blocker" : step.checked ? "verified" : "reference";
  status.textContent = step.blocker ? "CAD 간섭" : step.hold ? "체결품 확인 대기" : step.checked ? "CAD 경로 확인" : "조립 방향";
  el("task").textContent = step.task;
  el("check").textContent = step.check;
  el("note").textContent = step.note || "";
  el("note").hidden = !step.note;
  el("gear").textContent = step.stock || "";
  el("gear-block").hidden = !step.stock;
  el("detail-group").textContent = step.group;
  el("interference").hidden = !stop;
  if (stop) {
    el("stop-distance").textContent = mm(stop.remaining);
    el("stop-volume").textContent = `${fmt(stop.volume)} mm³`;
  }
  el("stop").hidden = !stop;
}

function selectStep(index) {
  if (!steps[index]) return;
  pause();
  if (state.issues && !needsCheck(steps[index])) {
    state.issues = false;
    el("issues-only").setAttribute("aria-pressed", "false");
    makeIndex();
  }
  state.index = index;
  state.ghost = Boolean(steps[index].blocker);
  state.section = false;
  const step = current();
  history.replaceState(null, "", `#${step.id}`);
  el("step-number").textContent = `${String(index + 1).padStart(2, "0")} / ${steps.length}`;
  el("step-title").textContent = step.title;
  el("section").hidden = !step.cut;
  el("picked").hidden = true;
  updateNavigation();
  details();
  scene?.show(step);
  applyView();
  position(stopData() ? limit() : 0);
}

function go(direction) {
  const list = candidates();
  const i = list.findIndex(item => item.index === state.index) + direction;
  if (list[i]) selectStep(list[i].index);
}

function play() {
  if (animation) {
    pause();
    return;
  }
  const end = limit();
  const start = state.position >= end - .004 ? 0 : state.position;
  const startTime = performance.now();
  const duration = Math.max(650, (end - start) * 2500);
  position(start);
  el("play").textContent = "정지";
  el("play").setAttribute("aria-pressed", "true");
  const tick = now => {
    const progress = Math.min(1, (now - startTime) / duration);
    position(start + (end - start) * progress);
    if (progress < 1) animation = requestAnimationFrame(tick);
    else pause();
  };
  animation = requestAnimationFrame(tick);
}

el("step-list").addEventListener("click", event => {
  const button = event.target.closest("[data-step]");
  if (button) selectStep(choose(button.dataset.step));
});
el("step-select").addEventListener("change", event => selectStep(choose(event.target.value)));
el("issues-only").addEventListener("click", () => {
  state.issues = !state.issues;
  el("issues-only").setAttribute("aria-pressed", String(state.issues));
  makeIndex();
  if (state.issues && !needsCheck(current())) selectStep(candidates()[0].index);
  else updateNavigation();
});
el("prev").addEventListener("click", () => go(-1));
el("next").addEventListener("click", () => go(1));
el("position").addEventListener("input", event => { pause(); position(+event.target.value / 1000); });
el("play").addEventListener("click", play);
el("start").addEventListener("click", () => { pause(); position(0); });
el("stop").addEventListener("click", () => { pause(); position(limit()); });
el("finish").addEventListener("click", () => { pause(); position(1); });
el("reset-view").addEventListener("click", () => scene?.resetView());
el("ghost").addEventListener("click", () => { state.ghost = !state.ghost; applyView(); });
el("section").addEventListener("click", () => { state.section = !state.section; applyView(); });

const fullscreen = el("expand");
fullscreen.hidden = !el("viewer").requestFullscreen;
fullscreen.addEventListener("click", async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await el("viewer").requestFullscreen();
  } catch (error) {
    console.warn("Fullscreen unavailable", error);
  }
});
document.addEventListener("fullscreenchange", () => {
  fullscreen.textContent = document.fullscreenElement ? "전체 화면 닫기" : "전체 화면";
});

const dialog = el("stock-dialog");
el("stock-open").addEventListener("click", () => dialog.showModal());
dialog.addEventListener("click", event => {
  const row = event.target.closest("[data-jump]");
  if (!row) return;
  dialog.close();
  selectStep(choose(row.dataset.jump));
  el("step-title").scrollIntoView({ block: "nearest" });
});
document.addEventListener("keydown", event => {
  if (dialog.open || event.altKey || event.ctrlKey || event.metaKey || event.target.matches("input, select, button, a")) return;
  const direction = { ArrowLeft: -1, ArrowRight: 1 }[event.key];
  if (direction) { event.preventDefault(); go(direction); }
});
window.addEventListener("hashchange", () => selectStep(choose(location.hash.slice(1))));

makeIndex();
selectStep(Math.max(0, choose(location.hash.slice(1))));
try {
  const viewer = new WalkthroughScene(el("canvas"), label => {
    el("picked").textContent = label;
    el("picked").hidden = !label;
  });
  stops = await viewer.load(hardware, steps);
  scene = viewer;
  el("model-status").hidden = true;
  for (const id of ["play", "position", "start", "finish"]) el(id).disabled = false;
  selectStep(state.index);
} catch (error) {
  console.error("Assembly CAD load failed", error);
  el("model-status").setAttribute("data-error", "");
  el("model-status").querySelector("p").textContent = "3D 모델을 열 수 없습니다. 페이지를 새로고침하고 WebGL이 켜져 있는지 확인하세요.";
}
