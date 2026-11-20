import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import { motionMatrix, neutral } from "../motion.js";
import { fastener } from "../hardware.js";
import { updateTube } from "../wiring.js";

const byId = id => document.getElementById(id);
const vector = xyz => new THREE.Vector3(...xyz);
const poseKey = pose => pose.join(",");
const palette = {
  camera: 0x55d7ff, motors: 0xefbd61, power: 0xff826e,
  "J1+": 0xff826e, "J1-": 0x8fb4ff, "J6-branch": 0x7ae4ab,
  "motor3-data": 0xdfa7ff, "motor6-data": 0x45cfe0, "motor6-power": 0xffb170,
  "fuse-in": 0xf1a1d6,
};
const labels = {
  Part000: "받침", Part001: "베어링 받침", Part002: "받침 상판",
  Part007: "목 회전판", Part010: "목 기둥", Part011: "목 요크",
  Part017: "목 좌우 모터", Part018: "목 상하 모터", Part038: "ID1 모터", ID1EH: "ID1 JST",
  HubHolder: "허브 덮개", CableSaddle: "케이블 트레이",
  Jaw_30_moving_jaw: "턱", Wdata: "DATA 분기", FuseID6: "턱 퓨즈",
  "J2+": "기존 J2 목 전원", "J3-D": "기존 J3 DATA", "J3-G": "기존 J3 GND",
  "USB-Camera": "카메라선", "J1+": "5 V 양극", "J1-": "5 V GND",
  "J6-branch": "J6 → WAGO", "motor3-data": "눈꺼풀 DATA",
  "motor1-return": "ID1 GND", "motor1-power": "ID1 전원", "motor1-data": "ID1 DATA",
  "motor5-return": "ID5 GND", "motor5-power": "ID5 전원", "motor5-data": "ID5 DATA",
  "motor6-data": "턱 DATA", "motor6-power": "턱 전원", "motor6-return": "턱 GND",
  "fuse-in": "퓨즈 입력", "12Vin+": "12 V 입력", "J7-return": "기존 J7 GND", "J7-data": "기존 J7 DATA",
};
const caption = id => labels[id] ?? id;
const family = id => id === "J1+" || id === "J1-" ? "power" : id === "USB-Camera" ? "camera" : "motors";
const issueWires = {
  j1: ["J1+", "J1-"],
  j6: ["J6-branch", "motor3-data", "motor6-data"],
  jaw: ["motor6-data"],
  moving: ["motor1-return", "motor1-power", "motor1-data", "USB-Camera"],
};
const issueNotes = {
  all: "수정 전후 버튼을 눌러 같은 자세의 경로와 분홍색 접촉 표시를 비교합니다.",
  j1: "덮개를 움직이면 뒤쪽 루프가 함께 움직입니다. 처짐은 조립 후 확인합니다.",
  j6: "초록선은 J6에서 고정 WAGO까지, 보라선과 하늘색 선은 WAGO에서 각 모터까지입니다.",
  jaw: "주황 점은 선택 자세에서 턱 DATA선이 가장 급하게 굽는 위치입니다.",
  moving: "추가 검사 자세에서 눈 ±8°와 턱 13°의 조합을 선택할 수 있습니다.",
  crossing: "덮개 30 mm, 목 좌우 ±60°와 상하 −15°/+6°의 네 자세를 비교할 수 있습니다.",
};

const isCombined = ([y, p, e, d, j]) => !e && !j && d === 30 && Math.abs(y) === 60 && [-15, 6].includes(p);
const pairKey = ({ wire, other }) => [wire, other].sort().join("|");
const crossingPairs = record => [...record.pairs, ...(record.reference_pairs ?? [])];
function summarize(report) {
  const cross = report.records.filter(row => isCombined(row.pose)).flatMap(crossingPairs);
  const worst = report.records.reduce((a, b) =>
    a.lengths["motor6-data"].minimum_bend_radius_mm <= b.lengths["motor6-data"].minimum_bend_radius_mm ? a : b);
  return {
    pairs: new Set(cross.map(pairKey)),
    wires: new Set(cross.flatMap(hit => [hit.wire, hit.other])),
    worst,
    moving: report.records.filter(row => row.solids.some(hit => hit.contact !== false &&
      issueWires.moving.includes(hit.wire))).length,
  };
}

function decode(encoded) {
  const text = atob(encoded);
  const bytes = new Uint8Array(text.length);
  for (let i = 0; i < bytes.length; i++) bytes[i] = text.charCodeAt(i);
  return bytes.buffer;
}

async function inputs() {
  const payload = byId("review-payload");
  if (payload) {
    const data = payload.dataset.encoding === "gzip-base64"
      ? await new Response(new Blob([decode(payload.textContent)]).stream()
        .pipeThrough(new DecompressionStream("gzip"))).json()
      : JSON.parse(payload.textContent);
    const buffers = Object.fromEntries(Object.entries(data.meshes).map(([id, value]) => [id, decode(value)]));
    return { ...data, model: decode(data.model), meshes: buffers };
  }
  const fetchFile = async (path, method = "json") => {
    const response = await fetch(path);
    if (!response.ok) throw new Error(path + " · " + response.status);
    return response[method]();
  };
  const [assembly, model, report, frames, wiring, hardware] = await Promise.all([
    fetchFile("../assets/assembly.json"), fetchFile("../assets/assembly.glb", "arrayBuffer"),
    fetchFile("./generated/wiring-check.json"), fetchFile("./generated/wiring-frames.json"),
    fetchFile("../assets/wiring.json"), fetchFile("./generated/hardware.json"),
  ]);
  const ids = ["Part000", "Part007", "CableSaddle"];
  const meshes = await Promise.all(ids.map(async id => [id, await fetchFile("./generated/" + id + ".stl", "arrayBuffer")]));
  return { assembly, model, report, frames, wiring, hardware, meshes: Object.fromEntries(meshes) };
}

async function start() {
  const data = await inputs();
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, .4, 1300);
  camera.up.set(0, 0, 1);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setClearColor(0x1b2a35);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.65));
  renderer.domElement.setAttribute("aria-label", "B16 CAD 배선과 검사 위치");
  const host = byId("scene");
  host.append(renderer.domElement);
  const orbit = new OrbitControls(camera, renderer.domElement);
  orbit.minDistance = 15;
  orbit.maxDistance = 900;
  const hemisphere = new THREE.HemisphereLight(0xddeefe, 0x647086, 1.8);
  const key = new THREE.DirectionalLight(0xffffff, 2.1);
  key.position.set(160, -220, 250);
  scene.add(hemisphere, key);
  const draw = () => renderer.render(scene, camera);
  orbit.addEventListener("change", draw);
  const resize = new ResizeObserver(() => {
    renderer.setSize(host.clientWidth, host.clientHeight, false);
    camera.aspect = host.clientWidth / host.clientHeight;
    camera.updateProjectionMatrix();
    draw();
  });
  resize.observe(host);

  const index = source => ({
    frames: new Map(source.frames.map(frame => [poseKey(frame.pose), frame])),
    records: new Map(source.report.records.map(record => [poseKey(record.pose), record])),
  });
  const versions = { after: index(data), before: data.before ? index(data.before) : undefined };
  const summaries = { after: summarize(data.report), before: data.before ? summarize(data.before.report) : undefined };
  const crossingWires = new Set([...summaries.after.wires, ...(summaries.before?.wires ?? [])]);
  if (summaries.before) {
    const { before, after } = summaries;
    const radius = summary => summary.worst.lengths["motor6-data"].minimum_bend_radius_mm.toFixed(3);
    byId("crossing-total").textContent = before.pairs.size + " → " + after.pairs.size + "쌍";
    byId("jaw-total").textContent = radius(before) + " → " + radius(after) + " mm";
    byId("moving-total").textContent = before.moving + " → " + after.moving + " / " + data.frames.length;
    byId("comparison-totals").hidden = false;
  }
  let version = "after";
  const rig = await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).parseAsync(data.model, "");
  scene.add(rig.scene);
  const stl = new STLLoader();
  const models = [];
  const modelPart = (node, part, versionOnly = null) => {
    node.updateMatrix();
    const base = node.matrix.clone();
    node.matrixAutoUpdate = false;
    models.push({ node, base, motion: part.motion || "fixed", shell: part.shell, versionOnly });
  };
  for (const part of data.assembly.parts) {
    let node = rig.scene.getObjectByName(part.name);
    if (!node) continue;
    if (part.cad_id.startsWith("Ballast") || part.cad_id.startsWith("HubRearClearance")) {
      node.visible = false;
      continue;
    }
    const geometry = data.meshes[part.cad_id];
    if (geometry) {
      node.removeFromParent();
      node = new THREE.Mesh(stl.parse(geometry));
      scene.add(node);
    }
    const material = new THREE.MeshStandardMaterial({
      color: part.shell ? 0xadbaca : part.section === "neck" ? 0x8697ad : 0x8393a1,
      roughness: .78, transparent: true, opacity: part.shell ? .12 : part.motion === "fixed" ? .26 : .43,
      depthWrite: false, side: THREE.DoubleSide,
    });
    node.traverse(child => { if (child.isMesh) child.material = material; });
    const beforeMesh = data.before?.meshes[part.cad_id];
    modelPart(node, part, beforeMesh ? "after" : null);
    if (beforeMesh) {
      const oldPart = new THREE.Mesh(stl.parse(decode(beforeMesh)), material);
      scene.add(oldPart);
      modelPart(oldPart, part, "before");
    }
  }
  for (const part of data.hardware) {
    if (part.id.startsWith("ballast")) continue;
    const { node, materials } = fastener(part);
    for (const material of materials) {
      material.transparent = true;
      material.opacity = .35;
      material.depthWrite = false;
    }
    scene.add(node);
    modelPart(node, part);
  }
  const beforeBlocks = new Map(data.before?.blocks.map(block => [block.id, block]));
  function modelBlock(block, versionOnly) {
    const material = new THREE.MeshStandardMaterial({
      color: block.kind === "fuse" ? 0x983a49 : 0x80958f, transparent: true, opacity: .48, depthWrite: false,
    });
    const node = new THREE.Mesh(new THREE.BoxGeometry(...block.size), material);
    node.position.set(...block.center);
    scene.add(node);
    modelPart(node, block, versionOnly);
  }
  for (const block of data.wiring.blocks) {
    const old = beforeBlocks.get(block.id);
    const changed = data.before && JSON.stringify(old) !== JSON.stringify(block);
    modelBlock(block, changed ? "after" : null);
    if (changed && old) modelBlock(old, "before");
  }

  const wires = new Map();
  const marks = new THREE.Group();
  scene.add(marks);
  const markShape = new THREE.SphereGeometry(1.5, 12, 8);
  const markerMaterial = color => new THREE.MeshBasicMaterial({ color, transparent: true, depthTest: false, depthWrite: false });
  const markColor = markerMaterial(0xff4a7c);
  const bendColor = markerMaterial(0xffbd6e);
  const pinColor = markerMaterial(0xe6f1f6);
  const cableMaterials = new Map(Object.entries(palette).map(([name, color]) => [
    name, new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: .27 }),
  ]));
  cableMaterials.set("neighbors", new THREE.MeshStandardMaterial({ color: 0xadb6df, transparent: true, opacity: .72, depthWrite: false }));
  byId("neighbors-label").hidden = !data.frames.some(frame => !!frame.neighbors);

  function focus(location, offset) {
    orbit.target.set(...location);
    camera.position.copy(orbit.target).add(vector(offset));
    orbit.update();
    draw();
  }
  function zoomBase() { focus([-7, 70, -78], [-114, 177, 71]); }
  function zoomNeck() { focus([0, -13, 28], [154, -213, 125]); }
  let mode = "neck";
  let timer;
  let extraPose;
  let issue = "all";
  const extra = byId("extra");
  const combined = byId("combined");
  extra.add(new Option("기본 자세", ""));
  for (const frame of data.frames) {
    const [y, p, e, d, j] = frame.pose;
    if (isCombined(frame.pose)) {
      const angle = n => (n > 0 ? "+" : "") + n + "°";
      combined.add(new Option(angle(y) + " / " + angle(p), poseKey(frame.pose)));
    }
    if (!e && !j) continue;
    extra.add(new Option([y + "°", p + "°", "눈 " + e + "°", "덮개 " + d + " mm", "턱 " + j + "°"].join(" · "), poseKey(frame.pose)));
  }
  byId("extra-label").hidden = extra.options.length === 1;
  byId("combined-label").hidden = combined.options.length === 1;
  byId("comparison").hidden = !data.before;

  function clearExtra() { extraPose = undefined; extra.value = ""; combined.value = ""; }
  function stop() {
    clearInterval(timer);
    timer = undefined;
    byId("play").setAttribute("aria-pressed", "false");
    byId("play").textContent = "왕복 재생";
  }

  function renderPose() {
    const pose = extraPose || (mode === "hatch" ? [0, 0, 0, Number(byId("drop").value), 0] :
      [Number(byId("yaw").value), Number(byId("pitch").value), 0, 0, 0]);
    const { frames, records } = versions[version];
    const frame = frames.get(poseKey(pose));
    const record = records.get(poseKey(pose));
    if (!frame || !record) throw new Error("선택한 자세의 검사 결과가 없습니다.");
    const [yaw, pitch, eye, drop, jaw] = pose;
    if (extraPose) {
      byId("yaw").value = yaw;
      byId("pitch").value = pitch;
      byId("drop").value = drop;
    }
    byId("yaw-value").textContent = yaw + "°";
    byId("pitch-value").textContent = pitch + "°";
    byId("drop-value").textContent = drop + " mm";
    const state = { ...neutral, neckYaw: yaw, neckPitch: pitch, eyePitch: eye, jaw };
    const motion = new Map(models.map(({ motion }) => [motion, motionMatrix(motion, state, drop)]));
    const showParts = !byId("wire-only").checked;
    for (const part of models) {
      part.node.matrix.multiplyMatrices(motion.get(part.motion), part.base);
      part.node.matrixWorldNeedsUpdate = true;
      part.node.visible = showParts && (!part.versionOnly || part.versionOnly === version) &&
        (!part.shell || byId("shell").checked);
    }
    const targeted = id => issue === "all" || (issue === "crossing" ? crossingWires.has(id) : issueWires[issue].includes(id));
    const selected = id => targeted(id) && byId(family(id)).checked;
    for (const node of wires.values()) node.visible = false;
    const drawWire = (path, key, visible) => {
      if (!visible) return;
      let node = wires.get(path.id);
      const material = cableMaterials.get(key);
      if (!node) {
        node = new THREE.Mesh(new THREE.BufferGeometry(), material);
        wires.set(path.id, node);
        scene.add(node);
      }
      node.material = material;
      updateTube(node, path.points.map(vector), path.d / 2);
      node.visible = true;
    };
    for (const path of frame.paths) {
      drawWire(path, cableMaterials.has(path.id) ? path.id : family(path.id), selected(path.id));
    }
    for (const path of frame.neighbors ?? []) {
      const highlighted = issue !== "all" && selected(path.id);
      drawWire(path, highlighted && cableMaterials.has(path.id) ? path.id : "neighbors",
        highlighted || (byId("neighbors").checked && targeted(path.id)));
    }

    const shown = hit => selected(hit.wire);
    const solid = record.solids.filter(shown);
    const pairs = record.pairs.filter(hit => shown(hit) || selected(hit.other));
    const self = (record.self_pairs ?? []).filter(shown);
    const references = (record.reference_pairs ?? []).filter(hit =>
      shown(hit) || (issue !== "all" && selected(hit.other)));
    const internalReferences = byId("neighbors").checked
      ? (record.neighbor_pairs ?? []).filter(hit => shown(hit) || selected(hit.other)) : [];
    const bends = Object.entries(record.lengths).filter(([id, row]) =>
      selected(id) && row.minimum_bend_radius_mm < row.bend_target_mm);
    const contacts = solid.filter(hit => hit.contact !== false).length;
    byId("result").textContent = "부품 접촉 " + contacts + "곳 · 0.25 mm 이내 " + (solid.length - contacts) +
      "곳 · 전선 겹침 " + pairs.length + "쌍 · 자기 겹침 " + self.length + "곳 · 기존 경로 교차 " +
      references.length + "쌍" + (byId("neighbors").checked ? " · 참조선끼리 " + internalReferences.length + "쌍" : "") +
      " · 굽힘 미달 " + bends.length + "가닥";
    const display = byId("positions");
    display.replaceChildren();
    marks.clear();
    function marker(point, color, text) {
      const dot = new THREE.Mesh(markShape, color);
      dot.position.set(...point);
      dot.renderOrder = 5;
      marks.add(dot);
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = text;
      button.onclick = () => focus(point, mode === "hatch" ? [-50, 90, 34] : [65, -94, 49]);
      display.append(button);
    }
    if (issue === "j1") {
      marker([-10, 62, -72.5-drop], pinColor, "J1 PCB 패드 2 · 5V IN");
      marker([-5, 62, -72.5-drop], pinColor, "J1 PCB 패드 1 · GND");
    }
    if (issue === "j6") {
      marker([-1, 46.45, -56.5-drop], pinColor, "J6 핀 3 · DATA");
    }
    if (byId("contacts").checked) {
      const visibleRefs = byId("neighbors").checked || issue !== "all" ? references : [];
      for (const hit of solid.concat(pairs, self, visibleRefs, internalReferences)) {
        const other = hit.part ?? (hit.other === hit.wire ? "자기 겹침" : hit.other);
        const badge = hit.overlap_mm ? hit.overlap_mm.toFixed(2) + " mm 겹침" :
          hit.contact === false ? "0.25 mm 이내" : "접촉";
        marker(hit.point, markColor, caption(hit.wire) + " · " + caption(other) + " · " + badge);
      }
    }
    if (byId("bends").checked || issue === "jaw") {
      const shownBends = issue === "jaw" && selected("motor6-data")
        ? [["motor6-data", record.lengths["motor6-data"]]] : bends;
      for (const [id, row] of shownBends.filter(([, row]) => row.bend_point)) {
        marker(row.bend_point, bendColor, caption(id) + " · R " + row.minimum_bend_radius_mm.toFixed(3) +
          " / 기준 " + row.bend_target_mm.toFixed(3) + " mm");
      }
    }
    const detail = mode === "hatch" && !extraPose ? "덮개 " + drop + " mm" : "목 좌우 " + yaw + "° · 상하 " + pitch + "°" +
      (extraPose ? " · 덮개 " + drop + " mm · 눈 " + eye + "° · 턱 " + jaw + "°" : "");
    const ids = issueWires[issue] ?? (issue === "crossing" ? ["fuse-in", "motor5-return"] : ["J1+", "J1-"]);
    const lengths = ids.filter(id => record.lengths[id]).map(id => caption(id) + " " +
      record.lengths[id].length_mm.toFixed(id.startsWith("J1") || id === "fuse-in" ? 3 : 1) + " mm");
    byId("status").textContent = detail + (lengths.length ? "  |  " + lengths.join(" · ") : "");
    byId("comparison-note").textContent = issueNotes[issue];
    byId("worst-pose").hidden = issue !== "jaw";
    document.body.dataset.pose = poseKey(pose);
    document.body.dataset.version = version;
    draw();
  }

  function setMode(next) {
    stop();
    clearExtra();
    mode = next;
    const cover = mode === "hatch";
    byId("hatch-mode").setAttribute("aria-pressed", cover);
    byId("neck-mode").setAttribute("aria-pressed", !cover);
    byId("hatch-controls").hidden = !cover;
    byId("neck-controls").hidden = cover;
    if (cover) zoomBase();
    else zoomNeck();
    renderPose();
  }

  byId("neck-mode").onclick = () => setMode("neck");
  byId("hatch-mode").onclick = () => setMode("hatch");
  byId("base-view").onclick = zoomBase;
  byId("neck-view").onclick = zoomNeck;
  byId("open-hatch").onclick = () => { stop(); clearExtra(); byId("drop").value = 30; renderPose(); };
  const selectPose = (current, other) => {
    stop();
    other.value = "";
    extraPose = current.value ? current.value.split(",").map(Number) : undefined;
    renderPose();
  };
  extra.onchange = () => selectPose(extra, combined);
  combined.onchange = () => selectPose(combined, extra);
  byId("worst-pose").onclick = () => {
    stop();
    clearExtra();
    extraPose = summaries[version].worst.pose;
    const key = poseKey(extraPose);
    if (isCombined(extraPose)) combined.value = key;
    if (extraPose[2] || extraPose[4]) extra.value = key;
    renderPose();
    focus(summaries[version].worst.lengths["motor6-data"].bend_point, [65, -94, 49]);
  };
  for (const name of ["before", "after"]) {
    byId(name).onclick = () => {
      if (!versions[name]) return;
      stop();
      version = name;
      for (const value of ["before", "after"]) byId(value).setAttribute("aria-pressed", value === name);
      renderPose();
    };
  }
  byId("wire-focus").onchange = event => {
    issue = event.target.value;
    if (issue === "j1") zoomBase();
    if (issue === "j6") focus([16, 42, -65], [70, 90, 52]);
    if (issue === "jaw") focus([-10, -21, -63], [74, -75, 51]);
    if (issue === "crossing") focus([0, 40, -67], [69, 155, -42]);
    if (issue === "moving") zoomNeck();
    renderPose();
  };
  for (const id of ["yaw", "pitch", "drop"]) {
    byId(id).addEventListener("input", () => { stop(); clearExtra(); renderPose(); });
  }
  for (const id of ["shell", "wire-only", "power", "camera", "motors", "contacts", "bends", "neighbors"]) {
    byId(id).addEventListener("input", renderPose);
  }
  for (const button of byId("corners").querySelectorAll("button")) {
    button.onclick = () => {
      stop();
      clearExtra();
      byId("yaw").value = button.dataset.yaw;
      byId("pitch").value = button.dataset.pitch;
      renderPose();
    };
  }
  byId("play").onclick = () => {
    if (timer) { stop(); return; }
    clearExtra();
    let step = 0;
    byId("play").textContent = "정지";
    byId("play").setAttribute("aria-pressed", "true");
    timer = setInterval(() => {
      const count = mode === "hatch" ? 30 : 24;
      let index = step++ % (2*count);
      if (index > count) index = 2*count-index;
      if (mode === "hatch") {
        byId("drop").value = index;
      } else {
        byId("yaw").value = -60+5*index;
        byId("pitch").value = -15+3*Math.round(7*index/count);
      }
      renderPose();
    }, 155);
  };
  zoomNeck();
  renderPose();
}

start().catch(error => {
  byId("status").textContent = "3D 검사 모델을 열지 못했습니다. " + error.message;
  console.error(error);
});
