import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
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
// Optional display hints (kept apart from the generated steps.json so a CAD re-export keeps them):
// focus / showParts highlight parts in steps that have no moving part, frameOn and view steer the camera.
let hints = data.hints ?? {};
if (!embedded) {
  try {
    const response = await fetch("hints.json", { cache: "no-cache" });
    if (response.ok) hints = await response.json();
  } catch (error) {
    console.warn("hints.json", error);
  }
}
for (const step of [...data.steps, ...(data.finalView ? [data.finalView] : [])]) {
  const hint = hints.steps?.[step.id];
  if (!hint) continue;
  for (const id of [...(hint.focus ?? []), ...(hint.showParts ?? []), ...(hint.frameOn ?? [])]) {
    if (!data.parts[id]) throw new Error(`hints.json: unknown part ${id} in ${step.id}`);
  }
  Object.assign(step, hint);
}
const steps = data.finalView ? [...data.steps, data.finalView] : data.steps;
const stops = data.stops ?? [];
const assemblyViews = data.assemblyViews ?? [];
const wireStates = data.wireStates ?? [];
const revision = data.revision ?? "B19";
const illustration = data.illustration === true;
const mainSteps = data.steps.filter(step => !step.continued).length;
const blockedSteps = data.steps.filter(step => step.issues.length).length;
document.title = `R5 ${revision} 조립 순서`;
el("revision").textContent = revision;
const statusText = `${illustration ? "CAD 조립 미리보기" : "CAD 조립 검사"} ${data.steps.length}단계`;
el("step-count").textContent = statusText + (blockedSteps ? ` · 확인 필요 ${blockedSteps}단계` : "");
if (illustration) el("tool-legend-label").textContent = "공구";
el("overview-link").hidden = document.documentElement.dataset.hosted !== "b25";

/* ---------- colours ---------- */
const COLOR = {
  background: 0xeef1f2,
  active: 0x2563eb,
  activeEdge: 0x0b2a7a,
  focus: 0xf08c00,
  focusEdge: 0x7a3d00,
  tool: 0x0f9f8a,
  edge: 0x2b3236,
};

/* ---------- renderer, scene, lights ---------- */
const renderer = new THREE.WebGLRenderer({ canvas: el("view"), antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(COLOR.background);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(32, 1, 1, 5000);
camera.up.set(0, 0, 1);
scene.add(camera);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
let repaint = true;
controls.addEventListener("change", () => { repaint = true; });
scene.add(new THREE.HemisphereLight(0xffffff, 0xaaa59b, 1.55));
// A head-light that follows the camera keeps every face readable while orbiting.
const key = new THREE.DirectionalLight(0xffffff, 1.7);
key.position.set(-0.5, 0.9, 0.4);
key.target.position.set(0, 0, -1);
camera.add(key, key.target);
const sun = new THREE.DirectionalLight(0xffffff, 0.55);
sun.position.set(200, -300, 400);
scene.add(sun);

const overlay = new THREE.Group();   // arrows, ghosts and markers drawn over the model
scene.add(overlay);
const stopMarker = new THREE.Mesh(new THREE.SphereGeometry(.9, 16, 8),
  new THREE.MeshBasicMaterial({ color: 0xe79022, depthTest: false }));
stopMarker.visible = false;
stopMarker.renderOrder = 6;
scene.add(stopMarker);

/* ---------- shared looks ---------- */
const looks = {
  active: new THREE.MeshStandardMaterial({ color: COLOR.active, roughness: .45, metalness: 0, side: THREE.DoubleSide,
    emissive: COLOR.active, emissiveIntensity: .18, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }),
  focus: new THREE.MeshStandardMaterial({ color: COLOR.focus, roughness: .5, side: THREE.DoubleSide,
    emissive: COLOR.focus, emissiveIntensity: .25, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }),
  tool: new THREE.MeshStandardMaterial({ color: COLOR.tool, roughness: .4, side: THREE.DoubleSide,
    emissive: COLOR.tool, emissiveIntensity: .2 }),
  faded: new THREE.MeshBasicMaterial({ color: 0xb9c2c6, transparent: true, opacity: .1, depthWrite: false, side: THREE.DoubleSide }),
  ghost: new THREE.MeshBasicMaterial({ color: COLOR.active, transparent: true, opacity: .25, depthWrite: false, side: THREE.DoubleSide }),
};
// Parts of the current step stay visible as a faint silhouette when another part hides them
// (a nut inside a closed slot, a nut under the floor).
const throughLooks = {
  active: new THREE.MeshBasicMaterial({ color: COLOR.active, transparent: true, opacity: .28, depthTest: false, depthWrite: false, side: THREE.DoubleSide }),
  focus: new THREE.MeshBasicMaterial({ color: COLOR.focus, transparent: true, opacity: .28, depthTest: false, depthWrite: false, side: THREE.DoubleSide }),
  tool: new THREE.MeshBasicMaterial({ color: COLOR.tool, transparent: true, opacity: .22, depthTest: false, depthWrite: false, side: THREE.DoubleSide }),
};
const edgeLooks = {
  base: new THREE.LineBasicMaterial({ color: COLOR.edge, transparent: true, opacity: .5 }),
  active: new THREE.LineBasicMaterial({ color: COLOR.activeEdge, transparent: true, opacity: .9 }),
  focus: new THREE.LineBasicMaterial({ color: COLOR.focusEdge, transparent: true, opacity: .9 }),
  faded: new THREE.LineBasicMaterial({ color: 0x55636a, transparent: true, opacity: .16, depthWrite: false }),
  ghost: new THREE.LineBasicMaterial({ color: COLOR.active, transparent: true, opacity: .75, depthTest: false }),
  tool: new THREE.LineBasicMaterial({ color: 0x075347, transparent: true, opacity: .8 }),
};
edgeLooks.ghost.userData.overlay = true;

/* ---------- model ---------- */
const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
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

const exterior = new Set(["Part073", "Part074", ...Object.keys(data.parts).filter(name => data.parts[name].guardPanel)]);
const baseCovers = new Set(["Part000", "Part002", "CableGate", "HubHolder"]);
const edgeCache = new Map();
const MAX_EDGE_TRIANGLES = 45000;

function triangleCount(geometry) {
  return (geometry.index ? geometry.index.count : geometry.attributes.position.count) / 3;
}

function prepare(node, id) {
  const meshes = [];
  node.traverse(mesh => {
    if (!mesh.isMesh) return;
    const base = mesh.material.clone();
    if (base.color) base.color.lerp(new THREE.Color(0xffffff), .32);
    base.side = THREE.DoubleSide;
    base.polygonOffset = true;
    base.polygonOffsetFactor = 1;
    base.polygonOffsetUnits = 1;
    if (data.parts[id]?.guardPanel) base.depthWrite = false;
    mesh.material = base;
    mesh.userData.partId = id;
    meshes.push({ mesh, base, edges: null });
  });
  return meshes;
}

const nodes = new Map();
for (const name of Object.keys(data.parts)) {
  const node = gltf.scene.getObjectByName(name);
  if (!node) throw new Error(`Missing model part: ${name}`);
  nodes.set(name, {
    id: name, node, meshes: prepare(node, name), look: "base", edged: false,
    position: node.position.clone(), quaternion: node.quaternion.clone(), posedPosition: node.position.clone(),
  });
}
const toolNodes = new Map();
for (const step of steps) {
  for (const tool of (step.toolPaths ?? []).flat()) {
    if (toolNodes.has(tool.id)) continue;
    const node = gltf.scene.getObjectByName(tool.id);
    if (!node) throw new Error(`Missing tool model: ${tool.id}`);
    node.visible = false;
    const entry = { id: tool.id, node, meshes: prepare(node, tool.id), look: "base", edged: false,
      position: node.position.clone(), bounds: new THREE.Box3().setFromObject(node) };
    setLook(entry, "tool");
    toolNodes.set(tool.id, entry);
  }
}

function ensureEdges(entry) {
  if (entry.edged) return;
  entry.edged = true;
  if (exterior.has(entry.id)) return;
  for (const item of entry.meshes) {
    const geometry = item.mesh.geometry;
    if (triangleCount(geometry) > MAX_EDGE_TRIANGLES) continue;
    let edges = edgeCache.get(geometry.uuid);
    if (!edges) {
      edges = new THREE.EdgesGeometry(geometry, 30);
      edgeCache.set(geometry.uuid, edges);
    }
    item.edges = new THREE.LineSegments(edges, edgeLooks[entry.look] ?? edgeLooks.base);
    item.edges.raycast = () => {};
    item.mesh.add(item.edges);
  }
}

function setLook(entry, look) {
  if (look !== "faded") ensureEdges(entry);
  if (entry.look === look) return;
  entry.look = look;
  for (const item of entry.meshes) {
    item.mesh.material = look === "base" ? item.base : looks[look];
    if (item.edges) item.edges.material = edgeLooks[look] ?? edgeLooks.base;
    const through = throughLooks[look];
    if (through && !item.through) {
      item.through = new THREE.Mesh(item.mesh.geometry, through);
      item.through.raycast = () => {};
      item.through.renderOrder = 3;
      item.mesh.add(item.through);
    }
    if (item.through) {
      item.through.visible = Boolean(through);
      if (through) item.through.material = through;
    }
  }
}

/* ---------- state ---------- */
const hinge = new THREE.Vector3(0, -39, 119);
const closed = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2);
const state = { index: 0, time: 0, playing: true, last: 0, stop: null, wirePose: null, part: null, plan: null, faded: new Set() };
const PRE_SECONDS = .8;
const HOLD_SECONDS = 1.4;
const TOOL_SECONDS = 1.25;
let cameraFrame;

function showExterior(id) {
  if (!el("hide-exterior").checked) return true;
  return !exterior.has(id) && !(steps[state.index].id === "final-view" && baseCovers.has(id));
}

function toolChoice() {
  return el("tool-select").value;
}

function activeTools(step) {
  const choices = step.toolPaths ?? [];
  const value = toolChoice();
  if (value === "none" || !choices.length) return [];
  if (value === "") return choices.slice(0, 6);
  return choices[Number(value)] ? [choices[Number(value)]] : [];
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
  if (tool.kind === "illustration") return tool.nut;
  if (tool.kind === "driver-axis") return `육각렌치 접근 범위 · ${tool.nut}`;
  const name = tool.kind === "socket" ? "소켓" : "스패너";
  return `${name} ${tool.size === 3 ? "5.5" : "4"} mm · ${tool.nut}`;
}

function pathLength(path) {
  let total = 0;
  for (let i = 1; i < path.length; i++) total += Math.hypot(...path[i].map((v, k) => v - path[i - 1][k]));
  return total;
}

function pathPoint(path, u) {
  const points = path.map(p => new THREE.Vector3(...p));
  if (points.length < 2) return points[0]?.clone() ?? new THREE.Vector3();
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

const ease = u => u < .5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
const clamp01 = u => Math.min(1, Math.max(0, u));

/* ---------- readable part names ---------- */
function partKind(id) {
  const label = data.parts[id]?.label ?? id;
  const text = `${id} ${label}`;
  const size = label.match(/M(\d)\s*[×x]\s*(\d+(?:\.\d+)?)/i);
  const metric = label.match(/\bM(\d)\b/i);
  const lower = text.toLowerCase();
  if (/insert|인서트/.test(lower)) return `${metric ? `M${metric[1]} ` : ""}인서트`;
  if (/washer|와셔/.test(lower)) return `${metric ? `M${metric[1]} ` : ""}와셔`;
  if (/nut|너트/.test(lower)) return `${metric ? `M${metric[1]} ` : ""}너트`;
  if (/screw|bolt|stud|나사|볼트/.test(lower) || size) return size ? `M${size[1]}×${size[2]} 나사` : "나사";
  if (/\bpin\b|핀|pivot/.test(lower)) return "핀";
  if (/head\d*$/i.test(id)) return "모터 케이스 나사";
  if (/alignment-gauge/.test(id)) return "정렬봉";
  if (/bearing|베어링/.test(lower)) return "베어링";
  if (/cabletie|cable tie|\btie\b|타이/.test(lower)) return "케이블 타이";
  let name = label.split(/\s+·\s+/)[0].trim();
  if (/^Part\d+$/.test(name)) name = id;
  return name.replace(/[_\s]*\d+$/, "") || name;
}

function summarize(ids, limit = 3) {
  const groups = new Map();
  for (const id of ids) {
    const kind = partKind(id);
    groups.set(kind, (groups.get(kind) ?? 0) + 1);
  }
  const rows = [...groups].map(([kind, count]) => count > 1 ? `${kind} ${count}개` : kind);
  return rows.length > limit ? `${rows.slice(0, limit).join(" · ")} 외 ${rows.length - limit}` : rows.join(" · ");
}

/* ---------- step list ---------- */
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

/* ---------- overlay helpers ---------- */
function clearOverlay() {
  for (const child of [...overlay.children]) {
    child.traverse(object => {
      if (object.userData.ownGeometry) object.geometry.dispose();
      if (object.userData.ownMaterial) object.material.dispose();
    });
  }
  overlay.clear();
}

const arrowShaft = new THREE.CylinderGeometry(1, 1, 1, 10, 1, true);
arrowShaft.rotateX(Math.PI / 2).translate(0, 0, .5);
const arrowHead = new THREE.ConeGeometry(1, 1, 16);
arrowHead.rotateX(Math.PI / 2).translate(0, 0, -.5);

function makeArrow(points, radius, color) {
  // points: world positions from start to end. Shaft segments plus a cone at the end.
  const group = new THREE.Group();
  const material = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: .9, depthTest: false });
  group.userData.material = material;
  const total = points.slice(1).reduce((sum, p, i) => sum + p.distanceTo(points[i]), 0);
  const headLength = Math.min(total * .45, radius * 7);
  const headRadius = radius * 2.6;
  const trimmed = points.map(p => p.clone());
  const last = trimmed.length - 1;
  const tail = trimmed[last].clone().sub(trimmed[last - 1]);
  const tailLength = tail.length();
  if (tailLength > headLength) trimmed[last].sub(tail.setLength(headLength));
  for (let i = 1; i < trimmed.length; i++) {
    const a = trimmed[i - 1], b = trimmed[i];
    const length = a.distanceTo(b);
    if (length < 1e-3) continue;
    const shaft = new THREE.Mesh(arrowShaft, material);
    shaft.position.copy(a);
    shaft.lookAt(b);
    shaft.scale.set(radius, radius, length);
    shaft.renderOrder = 8;
    group.add(shaft);
  }
  const head = new THREE.Mesh(arrowHead, material);
  head.position.copy(points[last]);
  head.lookAt(points[last - 1].clone().lerp(points[last], 2));   // cone tip points along travel
  head.scale.set(headRadius, headRadius, headLength);
  head.renderOrder = 8;
  group.add(head);
  return group;
}

function makeGhost(entry) {
  const ghost = entry.node.clone(true);
  ghost.traverse(object => {
    if (object.isMesh) {
      object.material = looks.ghost;
      object.raycast = () => {};
      object.renderOrder = 4;
    }
    if (object.isLineSegments) {
      object.material = edgeLooks.ghost;
      object.renderOrder = 7;
    }
  });
  ghost.visible = false;
  return ghost;
}

/* ---------- the step plan: what moves, how far, in what order ---------- */
function planStep(step) {
  const tools = activeTools(step);
  const focusIds = state.part ? [state.part]
    : state.stop ? state.stop.actors
    : [...(step.focus ?? []), ...(step.showParts ?? [])];
  const moves = (state.stop || state.wirePose) ? [] : step.moves.map(move => ({ ...move, path: move.path }));
  const n = moves.length;
  const moveSeconds = n ? Math.min(1.5, Math.max(.55, 4.2 / n)) : 0;
  const movesEnd = PRE_SECONDS * (n ? 1 : 0) + n * moveSeconds;
  const toolsEnd = movesEnd + tools.length * TOOL_SECONDS;
  const pulse = !n && !tools.length && focusIds.length ? 2.6 : 0;
  const total = Math.max(toolsEnd + (n || tools.length ? HOLD_SECONDS : 0), pulse);
  return { tools, focusIds, moves, moveSeconds, movesEnd, toolsEnd, total, arrows: [], ghosts: [] };
}

function scalePaths(plan, viewRadius) {
  // Very short insertion paths (a 12 mm drop seen from 300 mm away) read as "nothing moved".
  // Lengthen them for display only, keeping their direction and shape.
  const wanted = Math.max(viewRadius * .2, 14);
  for (const move of plan.moves) {
    const length = pathLength(move.path);
    if (length < 1e-6 || length >= wanted) continue;
    const factor = Math.min(3, wanted / length);
    move.path = move.path.map(point => point.map(v => v * factor));
  }
}

/* ---------- scene assembly for a step ---------- */
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
  }
  const plan = state.plan;
  const lids = step.closedLids ? ["Part078", "Part079"] : [];
  for (const id of step.fixed) {
    const entry = nodes.get(id);
    if (!entry) continue;
    entry.node.visible = showExterior(id);
    setLook(entry, state.faded.has(id) ? "faded" : "base");
  }
  for (const move of step.moves) {
    for (const id of move.ids) {
      const entry = nodes.get(id);
      if (entry) setLook(entry, "active");
    }
  }
  for (const id of step.showParts ?? []) {
    const entry = nodes.get(id);
    if (entry) entry.node.visible = true;
  }
  for (const id of plan.focusIds) {
    const entry = nodes.get(id);
    if (entry) setLook(entry, "focus");
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
    for (const pose of Object.values(state.stop.contactPose ?? {})) {
      const matrix = new THREE.Matrix4().set(...pose.matrix.flat());
      for (const id of pose.parts) applyActorPose(nodes.get(id), matrix);
    }
  }
  for (const entry of toolNodes.values()) entry.node.visible = false;
  el("tool-legend").hidden = !plan.tools.length;
  el("ghost-legend").hidden = !plan.moves.some(move => pathLength(move.path) > 0);
  el("focus-legend").hidden = !plan.focusIds.length;
  el("moving-legend").hidden = !plan.moves.length;
}

function buildOverlay(step, viewRadius) {
  clearOverlay();
  const plan = state.plan;
  plan.arrows = [];
  plan.ghosts = [];
  const radius = Math.min(1.4, Math.max(.35, viewRadius * .006));
  for (const move of plan.moves) {
    const length = pathLength(move.path);
    const visibleIds = move.ids.filter(id => nodes.has(id) && showExterior(id));
    if (!visibleIds.length || length < 1e-6) {
      plan.arrows.push(null);
      plan.ghosts.push([]);
      continue;
    }
    const center = partCenter(step, visibleIds[0]);
    const points = move.path.map(point => center.clone().add(new THREE.Vector3(...point)));
    const arrow = makeArrow(points, radius, COLOR.active);
    overlay.add(arrow);
    plan.arrows.push(arrow);
    const ghosts = [];
    for (const id of visibleIds) {
      const entry = nodes.get(id);
      const ghost = makeGhost(entry);
      ghost.position.copy(entry.posedPosition);
      ghost.quaternion.copy(entry.node.quaternion);
      overlay.add(ghost);
      ghosts.push(ghost);
    }
    plan.ghosts.push(ghosts);
  }
  for (const tools of plan.tools) {
    for (const tool of tools) {
      if (pathLength(tool.path) < 1e-6) continue;
      const seat = new THREE.Vector3(...tool.seat);
      const arrow = makeArrow(tool.path.map(point => seat.clone().add(new THREE.Vector3(...point))), radius * .8, COLOR.tool);
      arrow.visible = false;
      arrow.userData.tool = tool.id;
      overlay.add(arrow);
    }
  }
}

function applyActorPose(entry, matrix) {
  entry.posedPosition.copy(entry.position).applyMatrix4(matrix);
  entry.node.position.copy(entry.posedPosition);
  entry.node.quaternion.copy(entry.quaternion).premultiply(new THREE.Quaternion().setFromRotationMatrix(matrix));
}

/* ---------- timeline ---------- */
function place(step, time) {
  const plan = state.plan;
  const n = plan.moves.length;
  const pulse = .5 + .5 * Math.sin(time * Math.PI * 2 / 1.1);
  plan.moves.forEach((move, k) => {
    const begin = PRE_SECONDS + k * plan.moveSeconds;
    const u = ease(clamp01((time - begin) / plan.moveSeconds));
    const offset = pathPoint(move.path, u);
    for (const id of move.ids) {
      const entry = nodes.get(id);
      if (!entry) continue;
      entry.node.visible = (!move.temporary || u < 1) && showExterior(id);
      entry.node.position.copy(entry.posedPosition).add(offset);
    }
    const arrow = plan.arrows[k];
    if (arrow) {
      arrow.visible = u < 1;
      arrow.userData.material.opacity = time < begin ? .55 + .35 * pulse : .9;
    }
    for (const ghost of plan.ghosts[k] ?? []) ghost.visible = u < 1;
  });
  looks.ghost.opacity = .14 + .2 * pulse;
  if (!n && plan.focusIds.length) {
    looks.focus.emissiveIntensity = .15 + .5 * pulse;
  } else {
    looks.focus.emissiveIntensity = .25;
  }
  // tools enter one after another once the parts are seated
  plan.tools.forEach((tools, index) => {
    const begin = plan.movesEnd + index * TOOL_SECONDS;
    const local = (time - begin) / TOOL_SECONDS;
    const last = index === plan.tools.length - 1;
    const on = local >= 0 && (local < 1 || (last && time <= plan.total));
    const u = ease(clamp01(local / .7));
    for (const tool of tools) {
      const entry = toolNodes.get(tool.id);
      entry.node.visible = on;
      entry.node.position.copy(entry.position).add(pathPoint(tool.path, u));
    }
    for (const arrow of overlay.children) {
      if (!arrow.userData.tool || !tools.some(tool => tool.id === arrow.userData.tool)) continue;
      arrow.visible = on && u < 1;
    }
  });
  el("scrub").value = Math.round(clamp01(time / plan.total) * 1000);
  el("progress-bar").style.width = `${clamp01(time / plan.total) * 100}%`;
  phaseLabel(time);
  repaint = true;
}

function phaseLabel(time) {
  const plan = state.plan;
  let text = "";
  if (plan.moves.length && !plan.moves.some(move => pathLength(move.path) > 0)) {
    text = plan.tools.length && time >= plan.movesEnd && time < plan.toolsEnd ? "공구로 체결" : "부품 놓기";
  } else if (plan.moves.length) {
    if (time < PRE_SECONDS) text = "들어갈 자리";
    else if (time < plan.movesEnd) text = "끼우기";
    else if (time < plan.toolsEnd) text = "공구로 체결";
    else text = "완료 상태";
  } else if (plan.tools.length) {
    text = time < plan.toolsEnd ? "공구로 체결" : "완료 상태";
  } else if (plan.focusIds.length && !state.part && !state.stop) {
    text = "손으로 다루는 곳";
  }
  el("phase").textContent = text;
  el("phase").hidden = !text;
}

/* ---------- camera ---------- */
const raycaster = new THREE.Raycaster();

function focusTargets(step) {
  // Points the viewer has to see: where each moving part ends up, and where the tools seat.
  const plan = state.plan;
  if (state.part && data.parts[state.part]) {
    const size = data.parts[state.part].size;
    return [{ point: partCenter(step, state.part), margin: Math.max(size * .5, 2), size, path: [[0, 0, 0]], id: state.part }];
  }
  if (state.stop) return [{ point: stopPoint(step), margin: 2, size: 10, path: [[0, 0, 0]] }];
  const targets = [];
  for (const move of plan.moves) {
    for (const id of move.ids) {
      if (!data.parts[id] || !showExterior(id)) continue;
      targets.push({ point: partCenter(step, id), margin: Math.max(data.parts[id].size * .6, 2), size: data.parts[id].size, path: move.path, id });
    }
  }
  for (const tools of plan.tools) {
    for (const tool of tools) {
      const bounds = toolNodes.get(tool.id).bounds;
      targets.push({ point: new THREE.Vector3(...tool.seat), margin: 3, size: 6, path: tool.path, box: bounds });
    }
  }
  for (const id of plan.focusIds) {
    if (!data.parts[id]) continue;
    targets.push({ point: partCenter(step, id), margin: Math.max(data.parts[id].size * .5, 2), size: data.parts[id].size, path: [[0, 0, 0]], id });
  }
  if (state.stop) targets.push({ point: stopPoint(step), margin: 2, size: 10, path: [[0, 0, 0]] });
  return targets;
}

function sampleTargets(targets, count) {
  if (targets.length <= count) return targets;
  const picked = [targets[0]];
  while (picked.length < count) {
    let best = null, bestDistance = -1;
    for (const target of targets) {
      const distance = Math.min(...picked.map(p => p.point.distanceTo(target.point)));
      if (distance > bestDistance) { best = target; bestDistance = distance; }
    }
    picked.push(best);
  }
  return picked;
}

function occluderMeshes(step) {
  const moving = new Set(state.plan.moves.flatMap(move => move.ids));
  const meshes = [];
  for (const id of step.fixed) {
    const entry = nodes.get(id);
    if (!entry || !entry.node.visible || moving.has(id) || state.plan.focusIds.includes(id)) continue;
    for (const item of entry.meshes) meshes.push(item.mesh);
  }
  return meshes;
}

function blockersFrom(eye, targets, meshes, viewRadius) {
  const blocked = new Map();
  for (const target of targets) {
    const direction = target.point.clone().sub(eye);
    const distance = direction.length();
    const allowance = Math.max(target.margin, viewRadius * .18, 6);
    raycaster.set(eye, direction.normalize());
    raycaster.near = 0;
    raycaster.far = Math.max(0, distance - allowance);
    for (const hit of raycaster.intersectObjects(meshes, false)) {
      const id = hit.object.userData.partId;
      blocked.set(id, (blocked.get(id) ?? 0) + 1);
    }
  }
  return blocked;
}

function viewDirection(azimuth, elevation) {
  return new THREE.Vector3(Math.cos(azimuth) * Math.cos(elevation), Math.sin(azimuth) * Math.cos(elevation), Math.sin(elevation));
}

function frame(step, { animate = true } = {}) {
  const plan = state.plan;
  scene.updateMatrixWorld(true);
  const targets = focusTargets(step);
  // Bounds of the whole visible assembly give the context; bounds of the moving parts give the focus.
  const assembly = new THREE.Box3();
  for (const id of step.fixed) {
    const entry = nodes.get(id);
    if (entry?.node.visible && !exterior.has(id)) assembly.expandByObject(entry.node);
  }
  if (step.showWires || step.id === "final-view") {
    for (const id of step.fixed) {
      const entry = nodes.get(id);
      if (entry?.node.visible) assembly.expandByObject(entry.node);
    }
  }
  const focus = new THREE.Box3();
  const framed = !state.part && !state.stop && step.frameOn ? step.frameOn.filter(id => data.parts[id]) : [];
  for (const id of framed) {
    const c = partCenter(step, id), r = Math.max(data.parts[id].size / 2, 3);
    focus.expandByPoint(c.clone().addScalar(r)).expandByPoint(c.clone().addScalar(-r));
  }
  for (const target of framed.length ? [] : targets) {
    const r = Math.max(target.size / 2, 3);
    for (const offset of target.path) {
      const at = target.point.clone().add(new THREE.Vector3(...offset));
      focus.expandByPoint(at.clone().addScalar(r));
      focus.expandByPoint(at.clone().addScalar(-r));
    }
    if (target.box) for (const offset of target.path) focus.union(target.box.clone().translate(new THREE.Vector3(...offset)));
  }
  if (focus.isEmpty() && assembly.isEmpty()) return;
  const sphereOf = box => box.getBoundingSphere(new THREE.Sphere());
  const asm = assembly.isEmpty() ? sphereOf(focus) : sphereOf(assembly);
  const foc = focus.isEmpty() ? asm : sphereOf(focus);
  let center, radius;
  const wholeView = step.showWires || step.id === "final-view" || focus.isEmpty();
  const wanted = Math.max(foc.radius * 1.7 + 12, 42);
  if (wholeView || wanted >= asm.radius * .8) {
    const union = assembly.clone().union(focus.isEmpty() ? assembly : focus);
    const sphere = sphereOf(union);
    center = sphere.center;
    radius = Math.max(sphere.radius, 30);
  } else {
    center = foc.center.clone().lerp(asm.center, .15);
    radius = Math.max(wanted, foc.radius * 1.15 + center.distanceTo(foc.center));
  }
  scalePaths(plan, radius);

  // Preferred viewing direction: three-quarter view from the side the parts come from,
  // tilted so the insertion motion crosses the screen instead of pointing at the camera.
  const motion = new THREE.Vector3();
  for (const move of plan.moves) if (pathLength(move.path) > 0) motion.add(new THREE.Vector3(...move.path[0]).normalize());
  for (const tools of plan.tools) for (const tool of tools) if (pathLength(tool.path) > 0) motion.add(new THREE.Vector3(...tool.path[0]).normalize().multiplyScalar(.5));
  if (motion.lengthSq() > 1e-6) motion.normalize();
  const outward = foc.center.clone().sub(asm.center).setZ(0);
  let azimuth = Math.atan2(-0.88, 0.48);   // default: front-right
  const horizontal = Math.hypot(motion.x, motion.y);
  if (horizontal > .5) {
    const base = Math.atan2(motion.y, motion.x);
    const options = [base + .9, base - .9];
    azimuth = options.reduce((best, a) => angleGap(a, azimuth) < angleGap(best, azimuth) ? a : best);
  } else if (outward.length() > asm.radius * .25) {
    azimuth = Math.atan2(outward.y, outward.x);
  }
  let elevation = motion.z < -.6 ? -.5 : motion.z > .6 ? .62 : .5;
  if (step.bench && motion.z >= -.6) elevation = .55;
  if (step.view && !state.part && !state.stop) {
    azimuth = THREE.MathUtils.degToRad(step.view[0]);
    elevation = THREE.MathUtils.degToRad(step.view[1]);
  }

  const halfFov = THREE.MathUtils.degToRad(camera.fov / 2);
  const usable = Math.max(.45, 1 - stageInsets().total / el("stage").clientHeight);
  const fitFov = Math.min(Math.atan(Math.tan(halfFov) * usable), Math.atan(Math.tan(halfFov) * camera.aspect * .94));
  const distance = radius / Math.sin(fitFov) * .94;
  const meshes = occluderMeshes(step);
  const sample = sampleTargets(targets, 4);
  let best = null;
  // An explicit view in hints.json is kept as given; otherwise try nearby views with fewer blockers.
  const candidates = step.view && !state.part && !state.stop ? [[0, 0]]
    : [[0, 0], [.6, 0], [-.6, 0], [0, .35], [1.2, 0], [-1.2, 0], [0, -.9], [Math.PI, 0]];
  for (const [da, de] of candidates) {
    const e = Math.max(-1.2, Math.min(1.3, elevation + de));
    const dir = viewDirection(azimuth + da, e);
    const eye = center.clone().add(dir.clone().multiplyScalar(distance));
    const blocked = sample.length ? blockersFrom(eye, sample, meshes, radius) : new Map();
    const hits = [...blocked.values()].reduce((s, v) => s + v, 0);
    const score = hits * 10 + Math.abs(da) * 2 + Math.abs(de) * 3;
    if (!best || score < best.score) best = { score, dir, eye };
    if (hits === 0) break;
  }
  state.view = { center: center.clone(), position: best.eye.clone(), radius, targets: sample };
  moveCamera(center, best.eye, animate);
  updateFade(step, best.eye);
}

function angleGap(a, b) {
  return Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)));
}

function updateFade(step, eye = camera.position) {
  const view = state.view;
  scene.updateMatrixWorld(true);
  const next = new Set();
  if (view?.targets?.length && el("xray").checked) {
    const blocked = blockersFrom(eye, view.targets, occluderMeshes(step), view.radius);
    for (const id of blocked.keys()) next.add(id);
  }
  state.faded = next;
  for (const id of step.fixed) {
    const entry = nodes.get(id);
    if (!entry || entry.look === "active" || entry.look === "focus") continue;
    setLook(entry, next.has(id) ? "faded" : "base");
  }
  el("xray-legend").hidden = !next.size;
  repaint = true;
}

function moveCamera(center, position, animate = true) {
  const from = { center: controls.target.clone(), position: camera.position.clone() };
  cancelAnimationFrame(cameraFrame);
  if (!animate) {
    controls.target.copy(center);
    camera.position.copy(position);
    repaint = true;
    return;
  }
  const start = performance.now();
  const tween = now => {
    const k = Math.min(1, (now - start) / 650);
    const e = ease(k);
    controls.target.lerpVectors(from.center, center, e);
    camera.position.lerpVectors(from.position, position, e);
    repaint = true;
    if (k < 1) cameraFrame = requestAnimationFrame(tween);
  };
  cameraFrame = requestAnimationFrame(tween);
}

/* ---------- labels that follow the parts ---------- */
const projected = new THREE.Vector3();
function updateChip() {
  const chip = el("chip");
  const plan = state.plan;
  const ids = plan.moves.length ? plan.moves.flatMap(move => move.ids).filter(id => nodes.get(id)?.node.visible)
    : plan.focusIds.filter(id => nodes.get(id)?.node.visible);
  const toolIds = plan.tools.flat().map(tool => tool.id).filter(id => toolNodes.get(id)?.node.visible);
  const objects = toolIds.length && state.time >= plan.movesEnd ? toolIds.map(id => toolNodes.get(id).node) : ids.map(id => nodes.get(id).node);
  if (!objects.length || !chip.dataset.text) { chip.hidden = true; return; }
  const box = new THREE.Box3();
  for (const object of objects) box.expandByObject(object);
  box.getCenter(projected);
  projected.z = box.max.z;
  projected.project(camera);
  if (projected.z > 1) { chip.hidden = true; return; }
  const stage = el("stage");
  const x = (projected.x * .5 + .5) * stage.clientWidth;
  const y = (-projected.y * .5 + .5) * stage.clientHeight;
  chip.hidden = false;
  chip.textContent = toolIds.length && state.time >= plan.movesEnd ? chip.dataset.tool : chip.dataset.text;
  chip.classList.toggle("tool", Boolean(toolIds.length && state.time >= plan.movesEnd));
  chip.classList.toggle("focus", !plan.moves.length && !toolIds.length);
  const w = chip.offsetWidth;
  chip.style.left = `${Math.max(8, Math.min(stage.clientWidth - w - 8, x - w / 2))}px`;
  chip.style.top = `${Math.max(stageInsets().top - 6, Math.min(stage.clientHeight - 80, y - 46))}px`;
}

/* ---------- notes & card ---------- */
function updateNotes(step) {
  const notes = step.notes.slice();
  if (step.insertionClearance) {
    const { slide, lower } = step.insertionClearance;
    notes.push(`CAD 계산상 최소 여유 · 옆으로 밀 때 ${slide.continuous_lower_bound_mm} mm · 자리 맞출 때 ${lower.continuous_lower_bound_mm} mm`);
  }
  if (step.blinkDegrees !== undefined) notes.push(`${illustration ? "눈꺼풀 조립 자세" : "검사한 눈꺼풀 위치"} · ${step.blinkDegrees}°`);
  if (state.stop?.firstContactDegrees !== undefined)
    notes.push(`CAD에서 처음 닿는 각도 · ${state.stop.firstContactDegrees.toFixed(3)}°`);
  if (state.wirePose) {
    const [yaw, pitch, eye, , jaw] = state.wirePose.poseDegrees;
    const scope = state.wirePose.fullHarness ? "CAD 배선 모델 표시" : "카메라 경로만 표시";
    notes.push(`${scope} · 토크 해제 검사 자세 · 목 좌우 ${yaw}° · 상하 ${pitch}° · 눈 상하 ${eye}° · 턱 ${jaw}°`);
  }
  if (step.focusNote) notes.push(step.focusNote);
  el("notes").replaceChildren(...notes.map(note => Object.assign(document.createElement("li"), { textContent: note })));
}

function updateCaption(step, complete) {
  el("cap-step").textContent = complete ? "완성" : step.continued ? `${step.label} 이어서` : `${step.label}단계`;
  el("cap-section").textContent = step.section ?? "";
  el("cap-bench").hidden = !step.bench;
  el("cap-text").textContent = step.text;
  const plan = state.plan;
  const moving = plan.moves.flatMap(move => move.ids).filter(id => data.parts[id]);
  const chip = el("chip");
  chip.dataset.text = moving.length ? summarize(moving)
    : plan.focusIds.length ? (!state.part && !state.stop && step.focusLabel) || summarize(plan.focusIds) : "";
  const tool = plan.tools.flat()[0];
  chip.dataset.tool = tool ? (tool.kind === "illustration" ? tool.nut.split(" · ")[0] : toolLabel(tool).split(" · ")[0]) : "";
  const parts = el("parts");
  const rows = [];
  if (moving.length) rows.push(["이번에 넣는 부품", summarize(moving, 6), "active"]);
  if (plan.focusIds.length && !moving.length) rows.push(["손으로 다루는 곳", (!state.part && !state.stop && step.focusLabel) || summarize(plan.focusIds, 6), "focus"]);
  if (plan.tools.length) rows.push(["공구", [...new Set(plan.tools.flat().map(t => (t.kind === "illustration" ? t.nut : toolLabel(t)).split(" · ")[0]))].join(" · "), "tool"]);
  parts.replaceChildren(...rows.map(([title, value, kind]) => {
    const row = document.createElement("div");
    row.className = `part-row ${kind}`;
    row.innerHTML = "<i></i><span><b></b><span></span></span>";
    row.querySelector("b").textContent = title;
    row.querySelector("span span").textContent = value;
    return row;
  }));
  parts.hidden = !rows.length;
}

function clearStop(step) {
  if (!state.stop) return false;
  state.stop = null;
  el("stop-select").value = "";
  updateNotes(step);
  return true;
}

/* ---------- navigation ---------- */
function refresh(step, { reframe = true, restart = true } = {}) {
  state.plan = planStep(step);
  state.faded = new Set();
  if (reframe) state.view = null;
  show(step);
  updateCaption(step, step.id === "final-view");
  resize();
  if (reframe) frame(step);
  else updateFade(step);
  buildOverlay(step, state.view?.radius ?? 100);
  if (restart) state.time = state.playing ? 0 : state.plan.total;
  state.time = Math.min(state.time, state.plan.total);
  state.last = performance.now();
  place(step, state.time);
}

function go(index, stop = null) {
  state.index = Math.max(0, Math.min(steps.length - 1, index));
  state.stop = stop;
  state.wirePose = null;
  state.part = null;
  const step = steps[state.index];
  const complete = step.id === "final-view";
  if (complete) el("hide-exterior").checked = false;
  el("stop-select").value = stop?.id ?? "";
  el("wire-select").value = "";
  el("wire-view").hidden = !complete || !wireStates.length;
  el("play").hidden = complete;
  el("scrub").hidden = complete;
  el("prev").disabled = state.index === 0;
  el("next").disabled = state.index === steps.length - 1;
  history.replaceState(null, "", "#" + step.id);
  for (const button of document.querySelectorAll("#list button")) {
    button.classList.toggle("active", Number(button.dataset.index) === state.index);
  }
  const list = el("list");
  const active = list.querySelector("button.active");
  if (active) {
    const listBox = list.getBoundingClientRect();
    const rowBox = active.getBoundingClientRect();
    list.scrollTop += rowBox.top < listBox.top ? rowBox.top - listBox.top : Math.max(0, rowBox.bottom - listBox.bottom);
  }
  el("meta").innerHTML = (complete ? statusText : `<b>${step.label}</b> / ${mainSteps} · ${step.section}`) +
    (step.bench ? '<span class="bench">작업대</span>' : "");
  el("title").textContent = complete ? step.section : step.continued ? `${step.label} 이어서` : `${step.label}단계`;
  el("text").textContent = step.text;
  updateNotes(step);
  el("issues").hidden = !step.issues.length;
  el("issues").lastElementChild.replaceChildren(...step.issues.map(issue =>
    Object.assign(document.createElement("li"), { textContent: issue })));
  const choices = step.toolPaths ?? [];
  el("tool-view").hidden = !choices.length;
  el("tool-select").replaceChildren(
    new Option(choices.length > 1 ? "순서대로 모두 보기" : "보기", ""),
    ...choices.map((tools, i) => new Option(tools.map(toolLabel).join(" → "), String(i))),
    new Option(illustration ? "공구 숨기기" : "공구 경로 숨기기", "none"));
  const parts = complete ? data.inspectionParts ?? [] : [...new Set(step.moves.flatMap(move => move.ids))];
  el("part-view").hidden = !illustration || !parts.length;
  el("part-select").replaceChildren(new Option("단계 전체 보기", ""), ...parts.map(id => new Option(data.parts[id].label, id)));
  refresh(step);
}

function stageInsets() {
  const stage = el("stage");
  const top = el("caption").offsetHeight + 16;
  const bottom = Math.max(el("legend").offsetHeight, 32) + 22;
  return { top, bottom, total: top + bottom, height: stage.clientHeight };
}

function resize() {
  const canvas = renderer.domElement;
  const { clientWidth: w, clientHeight: h } = canvas.parentElement;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  // Shift the picture so the model is centred in the area between the caption and the legend.
  const { top, bottom } = stageInsets();
  camera.setViewOffset(w, h, 0, -(top - bottom) / 2, w, h);
  camera.updateProjectionMatrix();
  repaint = true;
}
addEventListener("resize", resize);

function setPlaying(playing) {
  state.playing = playing;
  el("play").textContent = playing ? "❚❚" : "▶︎";
  el("play").title = playing ? "멈춤 (Space)" : "재생 (Space)";
  el("stage-play").textContent = playing ? "❚❚" : "▶︎";
  el("stage-play").setAttribute("aria-label", playing ? "멈춤" : "재생");
}

function tick(now) {
  const step = steps[state.index];
  const plan = state.plan;
  if (state.playing && plan && plan.total > 0) {
    state.time += (now - state.last) / 1000;
    if (state.time > plan.total) state.time = 0;
    place(step, state.time);
  }
  state.last = now;
  controls.update();
  if (repaint) {
    renderer.render(scene, camera);
    updateChip();
    repaint = false;
  }
  requestAnimationFrame(tick);
}

el("prev").onclick = () => go(state.index - 1);
el("next").onclick = () => go(state.index + 1);
const togglePlay = () => {
  const step = steps[state.index];
  setPlaying(!state.playing);
  if (state.playing && state.time >= state.plan.total) state.time = 0;
  if (clearStop(step)) refresh(step);
};
el("play").onclick = togglePlay;
el("stage-play").onclick = togglePlay;
el("replay").onclick = () => {
  const step = steps[state.index];
  if (state.view) moveCamera(state.view.center, state.view.position);
  setPlaying(true);
  state.time = 0;
  place(step, 0);
  updateFade(step, state.view?.position);
};
el("scrub").oninput = event => {
  const step = steps[state.index];
  setPlaying(false);
  if (clearStop(step)) refresh(step);
  state.time = event.target.value / 1000 * state.plan.total;
  place(step, state.time);
};
el("hide-exterior").onchange = () => refresh(steps[state.index], { restart: false });
el("xray").onchange = () => updateFade(steps[state.index]);
el("tool-select").onchange = () => {
  const step = steps[state.index];
  clearStop(step);
  refresh(step);
};
let fadeTimer;
controls.addEventListener("end", () => {
  clearTimeout(fadeTimer);
  fadeTimer = setTimeout(() => updateFade(steps[state.index]), 120);
});
const inspectionViews = [...assemblyViews, ...stops];
el("stop-view").hidden = !inspectionViews.length;
if (assemblyViews.length) el("inspection-label").textContent = illustration ? "주요 조립 위치" : "검사 위치";
el("stop-select").append(...inspectionViews.map(view => new Option(view.label, view.id)));
el("stop-select").onchange = event => {
  const view = inspectionViews.find(location => location.id === event.target.value);
  if (!view) {
    go(state.index);
    return;
  }
  const step = steps.findIndex(row => row.id === view.stage);
  if (step < 0) throw new Error(`Missing inspection stage: ${view.stage}`);
  if (assemblyViews.includes(view)) {
    go(step);
    el("stop-select").value = view.id;
    return;
  }
  setPlaying(false);
  el("hide-exterior").checked = true;
  go(step, view);
};
el("wire-select").append(...wireStates.map(pose => new Option(pose.label, pose.id)));
el("wire-select").onchange = event => {
  const step = steps[state.index];
  state.wirePose = wireStates.find(pose => pose.id === event.target.value) ?? null;
  updateNotes(step);
  refresh(step, { reframe: false, restart: false });
};
el("part-select").onchange = event => {
  const step = steps[state.index];
  state.part = event.target.value || null;
  if (state.part) {
    if (step.id === "final-view") el("hide-exterior").checked = !exterior.has(state.part) && !baseCovers.has(state.part);
    setPlaying(false);
  }
  refresh(step);
};
addEventListener("keydown", event => {
  if (event.target instanceof Element && event.target.closest("button, input, select")) return;
  if (event.key === "ArrowRight") el("next").click();
  if (event.key === "ArrowLeft") el("prev").click();
  if (event.key === " ") { event.preventDefault(); togglePlay(); }
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
