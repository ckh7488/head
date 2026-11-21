import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { updateTube } from "../wiring.js";

const el = id => document.getElementById(id);
const embedded = el("embedded-data");
let data;
if (embedded) {
  data = JSON.parse(embedded.textContent);
} else {
  const response = await fetch("steps.json", { cache: "no-cache" });
  if (!response.ok) throw new Error(`steps.json: ${response.status}`);
  data = await response.json();
}
const steps = data.finalView ? [...data.steps, data.finalView] : data.steps;
const stops = data.stops ?? [];
const wireStates = data.wireStates ?? [];
const revision = data.revision ?? "B19";
const mainSteps = data.steps.filter(step => !step.continued).length;
const blockedSteps = data.steps.filter(step => step.issues.length).length;
document.title = `R5 ${revision} 조립 순서`;
el("revision").textContent = revision;
el("step-count").textContent = `CAD 조립 검사 ${data.steps.length}단계` + (blockedSteps ? ` · 확인 필요 ${blockedSteps}단계` : "");

const renderer = new THREE.WebGLRenderer({ canvas: el("view"), antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(0xf4f2ee);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(32, 1, 1, 5000);
camera.up.set(0, 0, 1);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
let repaint = true;
controls.addEventListener("change", () => { repaint = true; });
scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8478, 2.2));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(200, -300, 400);
scene.add(sun);
const paths = new THREE.Group();
scene.add(paths);
const stopMarker = new THREE.Mesh(new THREE.SphereGeometry(.9, 16, 8),
  new THREE.MeshBasicMaterial({ color: 0xe79022, depthTest: false }));
stopMarker.visible = false;
stopMarker.renderOrder = 6;
scene.add(stopMarker);

const loader = new GLTFLoader();
const gltf = embedded
  ? await loader.parseAsync(Uint8Array.from(atob(data.embeddedModel), char => char.charCodeAt(0)).buffer, "")
  : await loader.loadAsync(`model.glb?rev=${data.modelSha256 ?? data.cadSha256 ?? revision}`);
scene.add(gltf.scene);
const wiring = new THREE.Group();
const wireNodes = new Map();
for (const wire of data.wires ?? []) {
  const material = new THREE.MeshStandardMaterial({ color: wire.color, side: THREE.DoubleSide, roughness: .76 });
  const mesh = new THREE.Mesh(new THREE.BufferGeometry(), material);
  mesh.name = wire.label;
  updateTube(mesh, wire.points.map(point => new THREE.Vector3(...point)), wire.diameter / 2);
  wireNodes.set(wire.id, { mesh, wire, points: wire.points });
  wiring.add(mesh);
}
scene.add(wiring);
const nodes = new Map();
for (const name of Object.keys(data.parts)) {
  const node = gltf.scene.getObjectByName(name);
  if (!node) throw new Error(`Missing model part: ${name}`);
  const materials = [];
  node.traverse(mesh => {
    if (!mesh.isMesh) return;
    mesh.material = mesh.material.clone();
    mesh.material.side = THREE.DoubleSide;
    if (data.parts[name].guardPanel) mesh.material.depthWrite = false;
    materials.push(mesh.material);
  });
  nodes.set(name, {
    node, materials, position: node.position.clone(), quaternion: node.quaternion.clone(),
    posedPosition: node.position.clone(),
  });
}
const toolNodes = new Map();
for (const step of steps) {
  for (const tool of (step.toolPaths ?? []).flat()) {
    if (toolNodes.has(tool.id)) continue;
    const node = gltf.scene.getObjectByName(tool.id);
    if (!node) throw new Error(`Missing qualified tool model: ${tool.id}`);
    node.visible = false;
    toolNodes.set(tool.id, { node, position: node.position.clone(), bounds: new THREE.Box3().setFromObject(node) });
  }
}
const hinge = new THREE.Vector3(0, -39, 119);
const closed = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2);
const state = { index: 0, t: 1, playing: true, last: 0, stop: null, wirePose: null };
const MOVE_SECONDS = 1.3;
const HOLD_SECONDS = .9;
const exterior = new Set(["Part073", "Part074", ...Object.keys(data.parts).filter(name => data.parts[name].guardPanel)]);
let cameraFrame;

function showExterior(id) {
  return !exterior.has(id) || !el("hide-exterior").checked;
}

function selectedTools(step) {
  const name = el("tool-select").value;
  return name ? (step.toolPaths?.[Number(name)] ?? []) : [];
}

function actorPoint(step, id, coordinates) {
  const point = new THREE.Vector3(...coordinates);
  const matrix = state.wirePose?.actorPoses[id] ?? step.actorPoses?.[id];
  return matrix ? point.applyMatrix4(new THREE.Matrix4().set(...matrix.flat())) : point;
}

function partCenter(step, id) {
  return actorPoint(step, id, data.parts[id].center);
}

function stopPoint(step) {
  const stop = state.stop;
  const pose = stop.contactPose?.anchor;
  if (pose) return new THREE.Vector3(...stop.center).applyMatrix4(new THREE.Matrix4().set(...pose.matrix.flat()));
  return actorPoint(step, stop.actors[0], stop.center);
}

function toolLabel(tool) {
  if (tool.kind === "driver-axis") return `육각렌치 접근 범위 · ${tool.nut}`;
  const name = tool.kind === "socket" ? "소켓" : "스패너";
  return `${name} ${tool.size === 3 ? "5.5" : "4"} mm · ${tool.nut}`;
}

function pathPoint(path, u) {
  const points = path.map(p => new THREE.Vector3(...p));
  const lengths = points.slice(1).map((p, i) => p.distanceTo(points[i]));
  const distance = lengths.reduce((sum, length) => sum + length, 0);
  const durations = lengths.map(length => Math.max(length, distance * .3));
  const total = durations.reduce((sum, duration) => sum + duration, 0);
  let left = u * total;
  for (const [i, duration] of durations.entries()) {
    if (left <= duration || i === durations.length - 1) {
      return points[i].clone().lerp(points[i + 1], duration ? Math.min(1, left / duration) : 1);
    }
    left -= duration;
  }
  return new THREE.Vector3();
}

function makeList() {
  const list = el("list");
  let section = null;
  for (const [index, step] of steps.entries()) {
    if (step.section !== section) {
      section = step.section;
      const heading = document.createElement("h3");
      heading.textContent = section;
      list.append(heading);
    }
    const button = document.createElement("button");
    button.dataset.index = index;
    button.className = (step.continued ? "continued " : "") + (step.bench ? "bench" : "");
    const short = step.continued ? "이어서" : step.text.split(/(?<=[.다])\s/)[0];
    button.innerHTML = `<span class="n">${step.label}</span><span class="t"></span>`;
    button.querySelector(".t").textContent = short;
    button.addEventListener("click", () => go(index));
    list.append(button);
  }
}

function tint(entry, color, amount) {
  for (const material of entry.materials) {
    material.emissive = new THREE.Color(color);
    material.emissiveIntensity = amount;
  }
}

function pathLine(origin, path, color) {
  const points = path.map(point => origin.clone().add(new THREE.Vector3(...point)));
  const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),
    new THREE.LineDashedMaterial({ color, dashSize: 2, gapSize: 1.4, depthTest: false, transparent: true, opacity: .8 }));
  line.computeLineDistances();
  line.renderOrder = 5;
  paths.add(line);
}

function applyActorPose(entry, matrix) {
  entry.posedPosition.copy(entry.position).applyMatrix4(matrix);
  entry.node.position.copy(entry.posedPosition);
  entry.node.quaternion.copy(entry.quaternion).premultiply(new THREE.Quaternion().setFromRotationMatrix(matrix));
}

function show(step) {
  wiring.visible = Boolean(step.showWires);
  for (const [id, entry] of wireNodes) {
    const checkedPath = state.wirePose?.wirePoints[id];
    entry.mesh.visible = state.wirePose ? Boolean(checkedPath) : !step.wireIds || step.wireIds.includes(id);
    const points = checkedPath ?? entry.wire.points;
    if (points !== entry.points) {
      updateTube(entry.mesh, points.map(point => new THREE.Vector3(...point)), entry.wire.diameter / 2);
      entry.points = points;
    }
  }
  for (const entry of nodes.values()) {
    entry.node.visible = false;
    entry.node.position.copy(entry.position);
    entry.posedPosition.copy(entry.position);
    entry.node.quaternion.copy(entry.quaternion);
    tint(entry, 0x000000, 0);
  }
  const lids = step.closedLids ? ["Part078", "Part079"] : [];
  for (const id of step.fixed) {
    const entry = nodes.get(id);
    if (entry) entry.node.visible = showExterior(id);
  }
  for (const move of step.moves) {
    for (const id of move.ids) {
      const entry = nodes.get(id);
      if (!entry) continue;
      tint(entry, 0x1e6bff, .5);
    }
  }
  for (const id of lids) {
    const entry = nodes.get(id);
    if (!entry) continue;
    entry.posedPosition.sub(hinge).applyQuaternion(closed).add(hinge);
    entry.node.position.copy(entry.posedPosition);
    entry.node.quaternion.premultiply(closed);
  }
  for (const [id, pose] of Object.entries(state.wirePose?.actorPoses ?? step.actorPoses ?? {})) {
    applyActorPose(nodes.get(id), new THREE.Matrix4().set(...pose.flat()));
  }
  stopMarker.visible = Boolean(state.stop);
  el("stop-legend").hidden = !state.stop;
  if (state.stop) {
    stopMarker.position.copy(stopPoint(step));
    for (const id of state.stop.actors) tint(nodes.get(id), 0xe79022, .45);
    for (const pose of Object.values(state.stop.contactPose ?? {})) {
      const matrix = new THREE.Matrix4().set(...pose.matrix.flat());
      for (const id of pose.parts) applyActorPose(nodes.get(id), matrix);
    }
  }
  for (const line of paths.children) {
    line.geometry.dispose();
    line.material.dispose();
  }
  paths.clear();
  for (const entry of toolNodes.values()) entry.node.visible = false;
  const tools = selectedTools(step);
  el("tool-legend").hidden = !tools.length;
  if (state.stop) return;
  if (tools.length) {
    for (const tool of tools) pathLine(new THREE.Vector3(...tool.seat), tool.path, 0x10907d);
    return;
  }
  for (const move of step.moves) {
    if (!move.ids.some(showExterior)) continue;
    const center = partCenter(step, move.ids[0]);
    pathLine(center, move.path, 0x1e6bff);
  }
}

function place(step, t) {
  const tools = selectedTools(step);
  const stage = tools.length ? 1 : t;
  const count = step.moves.length;
  step.moves.forEach((move, k) => {
    const u = Math.min(1, Math.max(0, stage * count - k));
    const offset = pathPoint(move.path, u);
    for (const id of move.ids) {
      const entry = nodes.get(id);
      if (!entry) continue;
      entry.node.visible = (move.mounted || stage * count >= k) && showExterior(id);
      entry.node.position.copy(entry.posedPosition).add(offset);
    }
  });
  tools.forEach((tool, index) => {
    const entry = toolNodes.get(tool.id);
    const progress = t * tools.length - index;
    entry.node.visible = progress >= 0;
    entry.node.position.copy(entry.position).add(pathPoint(tool.path, Math.min(1, Math.max(0, progress))));
  });
  el("scrub").value = Math.round(t * 1000);
  repaint = true;
}

function frame(step) {
  if (state.stop) {
    const center = stopPoint(step);
    const side = Math.sign(center.x || 1);
    const offset = new THREE.Vector3(side * .65, -1, .65).normalize().multiplyScalar(52);
    moveCamera(center, center.clone().add(offset));
    return;
  }
  const box = new THREE.Box3();
  const tools = selectedTools(step);
  for (const tool of tools) {
    const { bounds } = toolNodes.get(tool.id);
    for (const offset of tool.path) box.union(bounds.clone().translate(new THREE.Vector3(...offset)));
  }
  for (const move of (tools.length ? [] : step.moves)) {
    for (const id of move.ids) {
      const part = data.parts[id];
      if (!part) continue;
      const c = partCenter(step, id);
      const r = Math.max(part.size / 2, 4);
      for (const p of move.path) {
        const at = c.clone().add(new THREE.Vector3(...p));
        box.expandByPoint(at.clone().addScalar(r));
        box.expandByPoint(at.clone().addScalar(-r));
      }
    }
  }
  if (box.isEmpty() && step.showWires) {
    for (const id of step.fixed) box.expandByObject(nodes.get(id).node);
  }
  if (box.isEmpty()) return;
  const middle = box.getCenter(new THREE.Vector3());
  const small = box.getSize(new THREE.Vector3()).length() < 40;
  for (const id of small ? [] : step.fixed) {
    if (step.showWires) {
      box.expandByObject(nodes.get(id).node);
      continue;
    }
    const part = data.parts[id];
    if (!part || part.size > 160) continue;
    const c = partCenter(step, id);
    if (c.distanceTo(middle) < 70) {
      box.expandByPoint(c.clone().addScalar(part.size / 2));
      box.expandByPoint(c.clone().addScalar(-part.size / 2));
    }
  }
  const center = box.getCenter(new THREE.Vector3());
  const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 30);
  const approach = new THREE.Vector3();
  for (const move of step.moves) approach.add(new THREE.Vector3(...move.path[0]).normalize());
  const dir = new THREE.Vector3(.55, -1, .65).normalize();
  if (approach.lengthSq() > 1e-6) dir.add(approach.normalize().multiplyScalar(.7)).normalize();
  const halfFov = THREE.MathUtils.degToRad(camera.fov / 2);
  const fitFov = Math.min(halfFov, Math.atan(Math.tan(halfFov) * camera.aspect));
  const distance = radius * (step.showWires ? 1.06 / Math.sin(fitFov) : 3.1);
  moveCamera(center, center.clone().add(dir.multiplyScalar(distance)));
}

function moveCamera(center, position) {
  const from = { center: controls.target.clone(), position: camera.position.clone() };
  cancelAnimationFrame(cameraFrame);
  const start = performance.now();
  const tween = now => {
    const k = Math.min(1, (now - start) / 450);
    const e = k * (2 - k);
    controls.target.lerpVectors(from.center, center, e);
    camera.position.lerpVectors(from.position, position, e);
    repaint = true;
    if (k < 1) cameraFrame = requestAnimationFrame(tween);
  };
  cameraFrame = requestAnimationFrame(tween);
}

function updateNotes(step) {
  const notes = step.notes.slice();
  if (step.insertionClearance) {
    const { slide, lower } = step.insertionClearance;
    notes.push(`CAD 계산상 최소 여유 · 옆으로 밀 때 ${slide.continuous_lower_bound_mm} mm · 자리 맞출 때 ${lower.continuous_lower_bound_mm} mm`);
  }
  if (step.blinkDegrees !== undefined) notes.push(`검사한 눈꺼풀 위치 · ${step.blinkDegrees}°`);
  if (state.stop?.firstContactDegrees !== undefined)
    notes.push(`CAD에서 처음 닿는 각도 · ${state.stop.firstContactDegrees.toFixed(3)}°`);
  if (state.wirePose) {
    const [yaw, pitch, eye, , jaw] = state.wirePose.poseDegrees;
    const scope = state.wirePose.fullHarness ? "CAD 배선 모델 표시" : "카메라 경로만 표시";
    notes.push(`${scope} · 토크 해제 검사 자세 · 목 좌우 ${yaw}° · 상하 ${pitch}° · 눈 상하 ${eye}° · 턱 ${jaw}°`);
  }
  el("notes").replaceChildren(...notes.map(note => Object.assign(document.createElement("li"), { textContent: note })));
}

function clearStop(step) {
  if (!state.stop) return false;
  state.stop = null;
  el("stop-select").value = "";
  updateNotes(step);
  return true;
}

function go(index, stop = null) {
  state.index = Math.max(0, Math.min(steps.length - 1, index));
  state.stop = stop;
  state.wirePose = null;
  const step = steps[state.index];
  const complete = step.id === "final-view";
  if (complete) el("hide-exterior").checked = false;
  el("stop-select").value = stop?.id ?? "";
  el("wire-select").value = "";
  el("wire-view").hidden = !complete || !wireStates.length;
  el("play").hidden = complete;
  el("scrub").hidden = complete;
  history.replaceState(null, "", "#" + step.id);
  for (const button of document.querySelectorAll("#list button")) {
    button.classList.toggle("active", Number(button.dataset.index) === state.index);
  }
  document.querySelector("#list button.active")?.scrollIntoView({ block: "nearest" });
  el("meta").innerHTML = (complete ? `CAD 조립 검사 ${data.steps.length}단계` : `<b>${step.label}</b> / ${mainSteps} · ${step.section}`) +
    (step.bench ? '<span class="bench">작업대</span>' : "");
  el("title").textContent = complete ? step.section : step.continued ? `${step.label} 이어서` : `${step.label}단계`;
  el("text").textContent = step.text;
  updateNotes(step);
  el("issues").hidden = !step.issues.length;
  el("issues").lastElementChild.replaceChildren(...step.issues.map(issue =>
    Object.assign(document.createElement("li"), { textContent: issue })));
  const choices = step.toolPaths ?? [];
  el("tool-view").hidden = !choices.length;
  el("tool-select").replaceChildren(new Option("공구 경로 숨기기", ""), ...choices.map((tools, i) =>
    new Option(tools.map(toolLabel).join(" → "), String(i))));
  if (!step.moves.length && choices.length) el("tool-select").selectedIndex = 1;
  show(step);
  state.t = state.playing ? 0 : 1;
  state.last = performance.now();
  place(step, state.t);
  frame(step);
}

function resize() {
  const canvas = renderer.domElement;
  const { clientWidth: w, clientHeight: h } = canvas.parentElement;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  repaint = true;
}
addEventListener("resize", resize);

function tick(now) {
  const step = steps[state.index];
  const moveCount = selectedTools(step).length || step.moves.length;
  if (state.playing && moveCount) {
    const previous = Math.min(1, state.t);
    const duration = MOVE_SECONDS * moveCount;
    state.t += (now - state.last) / 1000 / duration;
    if (state.t > 1 + HOLD_SECONDS / duration) state.t = 0;
    const progress = Math.min(1, state.t);
    if (progress !== previous) place(step, progress);
  }
  state.last = now;
  controls.update();
  if (repaint) {
    renderer.render(scene, camera);
    repaint = false;
  }
  requestAnimationFrame(tick);
}

el("prev").onclick = () => go(state.index - 1);
el("next").onclick = () => go(state.index + 1);
el("play").onclick = () => {
  const step = steps[state.index];
  state.playing = !state.playing;
  el("play").textContent = state.playing ? "❚❚" : "▶︎";
  if (clearStop(step)) {
    show(step);
    frame(step);
  }
};
el("scrub").oninput = event => {
  const step = steps[state.index];
  state.playing = false;
  el("play").textContent = "▶︎";
  state.t = event.target.value / 1000;
  if (clearStop(step)) {
    show(step);
    frame(step);
  }
  place(step, state.t);
};
el("hide-exterior").onchange = () => {
  const step = steps[state.index];
  show(step);
  place(step, Math.min(1, state.t));
};
el("tool-select").onchange = () => {
  const step = steps[state.index];
  clearStop(step);
  show(step);
  state.t = state.playing ? 0 : 1;
  state.last = performance.now();
  place(step, state.t);
  frame(step);
};
el("stop-view").hidden = !stops.length;
el("stop-select").append(...stops.map(stop => new Option(stop.label, stop.id)));
el("stop-select").onchange = event => {
  const stop = stops.find(location => location.id === event.target.value);
  if (!stop) {
    go(state.index);
    return;
  }
  const step = steps.findIndex(row => row.id === stop.stage);
  if (step < 0) throw new Error(`Missing stop inspection stage: ${stop.stage}`);
  state.playing = false;
  el("play").textContent = "▶︎";
  el("hide-exterior").checked = true;
  go(step, stop);
};
el("wire-select").append(...wireStates.map(pose => new Option(pose.label, pose.id)));
el("wire-select").onchange = event => {
  const step = steps[state.index];
  state.wirePose = wireStates.find(pose => pose.id === event.target.value) ?? null;
  updateNotes(step);
  show(step);
  place(step, 1);
};
addEventListener("keydown", event => {
  if (event.target instanceof Element && event.target.closest("button, input, select")) return;
  if (event.key === "ArrowRight") go(state.index + 1);
  if (event.key === "ArrowLeft") go(state.index - 1);
  if (event.key === " ") { event.preventDefault(); el("play").click(); }
});

addEventListener("hashchange", () => {
  const index = steps.findIndex(step => step.id === location.hash.slice(1));
  if (index >= 0 && index !== state.index) go(index);
});
makeList();
resize();
camera.position.set(250, -400, 300);
const start = steps.findIndex(step => step.id === location.hash.slice(1));
go(start < 0 ? (data.finalView ? steps.length - 1 : 0) : start);
el("loading").remove();
requestAnimationFrame(tick);
