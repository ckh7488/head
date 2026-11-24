import {
  AmbientLight, Box3, Box3Helper, BoxGeometry, Color, CylinderGeometry, DirectionalLight, Group,
  HemisphereLight, Mesh, MeshBasicMaterial, MeshStandardMaterial,
  PerspectiveCamera, Raycaster, RingGeometry, Scene, Vector2, Vector3, WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const data = JSON.parse(document.querySelector("#board-data").textContent);
const $ = selector => document.querySelector(selector);
const all = selector => [...document.querySelectorAll(selector)];
const ns = "http://www.w3.org/2000/svg";
const width = data.dim[0];
const height = data.dim[1];
$("#board-size").textContent = `${width} × ${height} mm`;
$("#board-stack").textContent = `FR-4 · ${data.layers.length}층 · 1.6 mm · 무연 HASL`;
const sch = $("#schematic");
const pcb = $("#pcb");
const initialBoard = [-1.6, -1.4, width + 3.2, height + 2.8];
const schMarks = new Map();
const refs = Object.keys(data.parts);
const fourLayer = data.layers.length === 4;
const copperWeight = fourLayer ? "외층 1 oz · 내층 0.5 oz" : "양면 2 oz";
const publishedTraceMinimum = fourLayer ? "다층 1 oz 최소 0.09 mm" : "2층 2 oz 최소 0.16 mm";
const layerLabels = { F: "윗면", In1: "L2 · GND", In2: "L3 · 전원", B: "밑면" };
let side = "F";
let view = "sch";
let selected = "";
let net = "";
let three;

const descriptions = {
  J1: "5 V 양극은 2번, GND는 1번입니다. 단자 피치 5.00 mm입니다. F1 7.5 A를 거쳐 눈과 눈꺼풀에 공급합니다.",
  J2: "12 V 양극은 2번, GND는 1번입니다. 단자 피치 5.00 mm입니다. F2 4 A를 거쳐 목 두 축에 공급합니다.",
  J3: "OpenRB의 GND와 DATA만 연결합니다. OpenRB EH 2번 VDD는 비웁니다.",
  H2: "H4와 함께 J2 잠금쇠를 받치는 구멍입니다.",
  H4: "H2와 함께 J2 잠금쇠를 받치는 구멍입니다.",
};
const limits = [
  ["외형", `${width} × ${height} mm`, "Economic 10 × 10 ~ 470 × 500 mm"],
  ["기판 두께", "1.60 mm", "1.6 mm 공칭 허용 범위 1.44–1.76 mm"],
  [`${data.layers.length}층 완성 동박`, copperWeight, "표준 적층"],
  ["표면처리", "무연 HASL", "Economic 밑면 실장과 함께 견적 확인"],
  ["최소 배선 폭", `${data.minTrack.toFixed(3)} mm`, publishedTraceMinimum],
  ["동박 간격 규칙", `${data.clearance.toFixed(3)} mm`, publishedTraceMinimum],
  ["도금 부품홀 최소 동박 링", `${data.minRing.toFixed(3)} mm · ${data.pthCount}홀`, fourLayer ? "다층 1 oz 권장 0.20 mm" : "2 oz 최소 0.254 mm"],
  ["관통 비아", `Ø${[...new Set(data.vias.map(via => via[3]))].sort().join("·")} 드릴 · ${data.vias.length}개`, "최소 Ø0.15 드릴 / Ø0.25 패드"],
  ["홀 공차", "홀은 PCB 탭에서 선택", "직경 +0.13/−0.08 mm · 위치 ±0.075 mm"],
  ["마스크 댐 기준", "TPS2557 최소 패드 간격 0.275 mm", fourLayer ? "1 oz 녹색 최소 0.10 mm" : "2 oz 최소 0.20 mm"],
  ["밑면 실장", `${data.pcbaCount}개 · IC 피치 0.65 mm`, "Economic IC 최소 피치 0.40 mm · 0402 이상"],
];

function element(tag, text, attributes = {}) {
  const item = document.createElement(tag);
  if (text != null) item.textContent = text;
  for (const [key, value] of Object.entries(attributes)) item.setAttribute(key, value);
  return item;
}

function svg(tag, attributes) {
  const item = document.createElementNS(ns, tag);
  for (const [key, value] of Object.entries(attributes)) item.setAttribute(key, value);
  return item;
}

function action(item, callback) {
  item.setAttribute("tabindex", "0");
  item.setAttribute("role", "button");
  item.addEventListener("click", callback);
  item.addEventListener("keydown", event => {
    if (["Enter", " "].includes(event.key)) {
      event.preventDefault();
      callback();
    }
  });
}

function table(headers, rows) {
  const out = element("table");
  const head = out.createTHead().insertRow();
  for (const name of headers) head.append(element("th", name, { scope: "col" }));
  const body = out.createTBody();
  for (const row of rows) {
    const line = body.insertRow();
    for (const value of row) {
      const cell = line.insertCell();
      if (value instanceof Node) cell.append(value);
      else cell.textContent = value;
    }
  }
  return out;
}

function fitBox(box) {
  const padding = 3.5;
  return [box.x - padding, box.y - padding, box.width + 2 * padding, box.height + 2 * padding];
}

function setBox(root, values) {
  root.setAttribute("viewBox", values.join(" "));
}

function putInside(input, output) {
  const source = new DOMParser().parseFromString(input, "image/svg+xml").documentElement;
  output.append(...[...source.children].filter(item => !["title", "desc"].includes(item.localName))
    .map(item => document.importNode(item, true)));
}

const schBox = fitBox(sch.getBBox());
setBox(sch, schBox);
const overlay = svg("g", {});
for (const candidate of sch.querySelectorAll("g.stroked-text > desc")) {
  const ref = candidate.textContent.trim();
  if (!data.parts[ref] || schMarks.has(ref)) continue;
  const bounds = candidate.parentElement.getBBox();
  if (!bounds.width) continue;
  const mark = svg("rect", { x: bounds.x - .65, y: bounds.y - .65, width: bounds.width + 1.3,
    height: bounds.height + 1.3, rx: .3, class: "sch-hot", "data-ref": ref, "aria-label": ref });
  action(mark, () => choose(ref));
  overlay.append(mark);
  schMarks.set(ref, mark);
}
sch.append(overlay);

function navigateSvg(root) {
  const pos = event => {
    const point = new DOMPoint(event.clientX, event.clientY);
    return point.matrixTransform(root.getScreenCTM().inverse());
  };
  let drag;
  root.addEventListener("wheel", event => {
    event.preventDefault();
    const p = pos(event);
    zoomSvg(root, event.deltaY < 0 ? .82 : 1.22, p);
  }, { passive: false });
  root.addEventListener("pointerdown", event => {
    if (event.button !== 0 || event.target.closest('[role="button"]')) return;
    drag = pos(event);
    root.setPointerCapture(event.pointerId);
  });
  root.addEventListener("pointermove", event => {
    if (!drag) return;
    const { x, y, width, height } = root.viewBox.baseVal;
    const p = pos(event);
    setBox(root, [x + drag.x - p.x, y + drag.y - p.y, width, height]);
  });
  root.addEventListener("lostpointercapture", () => { drag = null; });
}
navigateSvg(sch);
navigateSvg(pcb);

function zoomSvg(root, factor, point) {
  const { x, y, width, height } = root.viewBox.baseVal;
  if (width * factor < (root === sch ? 10 : 3) || width * factor > 800) return;
  const { x: cx, y: cy } = point || { x: x + width / 2, y: y + height / 2 };
  setBox(root, [cx + (x - cx) * factor, cy + (y - cy) * factor, width * factor, height * factor]);
}

const px = x => side === "B" ? width - x + .025 : x + .025;
const py = y => y + .025;

function showBoard() {
  pcb.replaceChildren();
  const real = svg("g", { transform: side === "B" ? `translate(${width + .05} 0) scale(-1 1)` : "" });
  if ($("#copper-toggle").checked) {
    const copper = svg("g", { opacity: .68, "data-layer": side + ".Cu" });
    putInside(data.drawings[side + "-copper"], copper);
    real.append(copper);
  }
  if ($("#silk-toggle").checked && data.drawings[side + "-silk"]) putInside(data.drawings[side + "-silk"], real);
  putInside(data.drawings["F-edge"], real);
  pcb.append(real);

  if (net) {
    for (const [name, layer, a, b, trackWidth] of data.tracks) {
      if (name === net && side === layer) pcb.append(svg("line", { x1: px(a[0]), y1: py(a[1]),
        x2: px(b[0]), y2: py(b[1]), stroke: "#fff494", "stroke-width": Math.min(trackWidth, 1.4),
        "stroke-linecap": "round", "pointer-events": "none" }));
    }
    for (const [name, xy, diameter] of data.vias) {
      if (name === net) pcb.append(svg("circle", { cx: px(xy[0]), cy: py(xy[1]), r: diameter / 2,
        fill: "none", stroke: "#fff494", "stroke-width": ".12", "pointer-events": "none" }));
    }
  }
  for (const [ref, part] of Object.entries(data.parts)) {
    if (part.side !== side && !part.pads.some(pad => pad.drill[0])) continue;
    const marker = svg("circle", { cx: px(part.xy[0]), cy: py(part.xy[1]), r: .62,
      fill: "transparent", class: "board-part" + (ref === selected ? " active" : ""), "aria-label": ref });
    action(marker, () => choose(ref));
    pcb.append(marker);
    for (const pad of part.pads) {
      if (!pad.layers.includes(side) && !pad.drill[0]) continue;
      if (pad.drill[0]) pcb.append(svg("circle", { cx: px(pad.xy[0]), cy: py(pad.xy[1]), r: pad.drill[0] / 2,
        fill: "#15231c", "pointer-events": "none" }));
      const target = svg("circle", { cx: px(pad.xy[0]), cy: py(pad.xy[1]),
        r: Math.max(.34, Math.min(...pad.size) / 2), fill: "transparent",
        class: "board-pad" + (pad.net && pad.net === net ? " active" : ""),
        "aria-label": [ref, pad.id, pad.net].filter(Boolean).join(" "), "data-pad": ref + "." + pad.id });
      action(target, () => choose(ref, pad.net.startsWith("unconnected-") ? "" : pad.net));
      pcb.append(target);
    }
  }
  if ($("#ref-toggle").checked) {
    for (const [ref, part] of Object.entries(data.parts)) {
      if (part.side !== side && ref !== selected) continue;
      const mark = svg("text", { x: px(part.xy[0]), y: py(part.xy[1]) - 1.05,
        class: "board-ref" + (ref === selected ? " active" : ""), "aria-label": ref });
      mark.textContent = ref;
      action(mark, () => choose(ref));
      pcb.append(mark);
    }
  }
  if (selected) {
    const choice = data.parts[selected];
    if (choice.side === side || choice.pads.some(pad => pad.drill[0])) {
      const [x, y] = choice.xy;
      pcb.append(svg("path", { d: `M${px(x) - 1.3} ${py(y)}h2.6 M${px(x)} ${py(y) - 1.3}v2.6`,
        stroke: "#fff0a4", "stroke-width": .12, "pointer-events": "none" }));
    }
  }
}

function partRow(ref) {
  const part = data.parts[ref];
  const selection = $("#selection");
  selection.replaceChildren(element("h2", ref), element("p", part.value), element("p", descriptions[ref] || part.notes));
  const summary = element("dl");
  for (const [label, value] of [
    ["부품", part.mpn],
    ["실장", part.jlc ? "밑면 · JLCPCB " + part.jlc : part.populate === "NATIVE" ? "기판 형상" : "윗면 · 수납땜"],
    ["풋프린트", part.footprint.split(":").pop()],
    ["좌표", part.xy.map((p, i) => (data.origin[i] + p).toFixed(3)).join(" / ") + " mm"],
    ...(part.placement ? [["CPL 회전", part.placement.Rotation + "°"]] : []),
  ]) summary.append(element("dt", label), element("dd", value));
  selection.append(summary);
  const pins = part.pads.filter(pad => pad.id || pad.drill[0]).map(pad => {
    const connection = pad.net.startsWith("unconnected-") ? "미연결"
      : pad.net ? element("button", pad.net.replace(/^\//, ""), { type: "button" }) : "—";
    if (connection instanceof Node) connection.addEventListener("click", () => choose(ref, pad.net));
    const drill = pad.drill[0] ? "Ø" + pad.drill[0].toFixed(2) : "—";
    return [pad.id || "홀", connection, pad.size.map(size => size.toFixed(2)).join("×"), drill];
  });
  $("#pins").replaceChildren(table(["핀", "넷", "패드 mm", "드릴 mm"], pins));
  const info = $("#net-info");
  info.replaceChildren();
  if (net) {
    const connected = refs.flatMap(name => data.parts[name].pads.filter(pad => pad.net === net).map(pad => name + "." + pad.id));
    info.append(element("strong", net.replace(/^\//, "")), element("p", connected.join(" · ")));
  }
}

function choose(ref, connection = "") {
  if (!data.parts[ref]) return;
  selected = ref;
  net = connection;
  $("#part").value = ref;
  for (const [name, mark] of schMarks) mark.classList.toggle("selected", name === ref);
  partRow(ref);
  if (view === "pcb") showBoard();
  if (three) highlight3d();
}

function setSide(next) {
  side = next;
  for (const button of all("[data-side]")) button.setAttribute("aria-pressed", String(button.dataset.side === side));
  showBoard();
}

function frame(ref) {
  if (ref === "all") {
    setBox(sch, schBox);
    return;
  }
  choose(ref);
  const mark = schMarks.get(ref);
  if (!mark) return;
  const { x, y } = mark.getBBox();
  const rect = ref === "U2" ? [x - 64, y - 48, 143, 110] : [x - 55, y - 34, 112, 81];
  setBox(sch, rect);
}

function setView(next) {
  view = next;
  for (const item of all("[data-view]")) item.setAttribute("aria-pressed", String(item.dataset.view === view));
  for (const pane of all("[data-pane]")) pane.hidden = pane.dataset.pane !== view;
  $("#workbench").hidden = view === "order";
  $("#order").hidden = view !== "order";
  $("#sheet-actions").hidden = view !== "sch";
  $("#board-actions").hidden = view !== "pcb";
  $("#model-actions").hidden = view !== "model";
  $("#caption").textContent = {
    sch: "부품 번호를 누르면 핀과 연결 회로를 확인합니다. 드래그로 이동하고 휠로 확대합니다.",
    pcb: "KiCad의 동박·실크 도면입니다. 패드를 누르면 같은 넷의 배선과 패드가 강조됩니다.",
    model: "드래그로 회전하고 휠로 확대합니다. 부품을 누르면 핀 정보를 확인합니다.",
  }[view] || "";
  if (view === "pcb") setSide(side);
  if (view === "model") {
    if (!three) start3d();
    else resize3d();
  }
}

const boardCenter = new Vector3(width / 2000, 0, height / 2000);
const status = $("#model-status");

function limiterBody(ref) {
  const part = data.parts[ref];
  const [x, z] = part.xy;
  const pin = part.pads.find(pad => pad.id === "1");
  const body = new Group();
  body.name = ref;
  body.position.set(x / 1000, 0, z / 1000);
  const caseMesh = new Mesh(new BoxGeometry(.003, .001, .003),
    new MeshStandardMaterial({ color: "#252725", roughness: .8 }));
  caseMesh.position.y = -.0005;
  const dot = new Mesh(new CylinderGeometry(.00014, .00014, .000025, 16),
    new MeshBasicMaterial({ color: "#aeb4ac" }));
  dot.position.set((pin.xy[0] - x) * .0007, -.00101, (pin.xy[1] - z) * .0007);
  body.add(caseMesh, dot);
  return body;
}

function start3d() {
  if (three) return;
  const target = $("#model-canvas");
  let renderer;
  try { renderer = new WebGLRenderer({ antialias: true }); }
  catch { status.textContent = "브라우저의 WebGL 2 지원이 필요합니다. PCB 탭에서 동일 기판을 확인할 수 있습니다."; return; }
  target.append(renderer.domElement);
  const scene = new Scene();
  scene.background = new Color("#e0e7de");
  const camera = new PerspectiveCamera(37, 1, .0001, 5);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.minDistance = .013;
  controls.maxDistance = .55;
  scene.add(new AmbientLight("#ffffff", .72), new HemisphereLight("#ffffff", "#2a3b2c", 1.6));
  const light = new DirectionalLight("#fff4de", 2.3);
  light.position.set(.12, .20, .14);
  const underside = new DirectionalLight("#eef4ff", 1.55);
  underside.position.set(-.06, -.18, .10);
  scene.add(light, underside);
  three = { renderer, scene, camera, controls, target, bodies: new Map(), marker: null };
  controls.addEventListener("change", draw3d);
  new ResizeObserver(resize3d).observe(target);
  orient3d("iso");
  status.textContent = "KiCad 3D 모델을 읽는 중";
  const binary = Uint8Array.from(atob(data.model), symbol => symbol.charCodeAt(0));
  new GLTFLoader().parse(binary.buffer, "", result => {
    scene.add(result.scene);
    result.scene.traverse(item => { if (data.parts[item.name]) three.bodies.set(item.name, item); });
    const outlines = ["U1", "U2", "U3"].filter(ref => data.parts[ref] && !three.bodies.has(ref));
    for (const ref of outlines) {
      const body = limiterBody(ref);
      scene.add(body);
      three.bodies.set(ref, body);
    }
    const missing = refs.filter(ref => data.parts[ref].populate === "YES" && !three.bodies.has(ref));
    const notes = [`${three.bodies.size}개 부품`, "KiCad 배치"];
    if (outlines.length) notes.push(`${outlines.join("·")}는 TI 치수의 외형과 1번 핀 표시`);
    if (missing.length) notes.push(`${missing.join("·")}는 PCB 탭에서 패드 확인`);
    status.textContent = notes.join(" · ");
    highlight3d();
  }, () => { status.textContent = "3D 파일을 읽지 못했습니다. PCB 탭을 사용하세요."; });
  let down;
  renderer.domElement.addEventListener("pointerdown", event => { down = [event.clientX, event.clientY]; });
  renderer.domElement.addEventListener("pointerup", event => {
    if (!down || Math.hypot(event.clientX - down[0], event.clientY - down[1]) > 5) return;
    const rect = renderer.domElement.getBoundingClientRect();
    const point = new Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    const ray = new Raycaster();
    ray.setFromCamera(point, camera);
    const hit = ray.intersectObjects([...three.bodies.values()], true)[0];
    for (let object = hit?.object; object; object = object.parent) {
      if (data.parts[object.name]) { choose(object.name); break; }
    }
  });
}

function draw3d() {
  if (view === "model" && three) three.renderer.render(three.scene, three.camera);
}

function resize3d() {
  if (!three || view !== "model") return;
  const { clientWidth, clientHeight } = three.target;
  if (!clientWidth || !clientHeight) return;
  three.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  three.renderer.setSize(clientWidth, clientHeight, false);
  three.camera.aspect = clientWidth / clientHeight;
  three.camera.updateProjectionMatrix();
  draw3d();
}

function orient3d(preset) {
  if (!three) return;
  const offset = {
    top: new Vector3(0, .127, .00001), bottom: new Vector3(0, -.127, .00001),
    iso: new Vector3(.057, .087, .095),
  }[preset];
  three.camera.position.copy(boardCenter).add(offset);
  three.controls.target.copy(boardCenter);
  three.controls.update();
  resize3d();
}

function highlight3d() {
  if (!three) return;
  if (three.marker) {
    three.scene.remove(three.marker);
    three.marker.geometry.dispose();
    three.marker.material.dispose();
  }
  three.marker = null;
  if (!selected) return;
  const object = three.bodies.get(selected);
  if (object) three.marker = new Box3Helper(new Box3().setFromObject(object), "#ffd55a");
  else {
    const { xy, side } = data.parts[selected];
    three.marker = new Mesh(new RingGeometry(.0013, .00165, 24),
      new MeshBasicMaterial({ color: "#c68a14", depthTest: false, side: 2 }));
    three.marker.position.set(xy[0] / 1000, side === "F" ? .002 : -.0005, xy[1] / 1000);
    three.marker.rotation.x = Math.PI / 2;
  }
  three.scene.add(three.marker);
  draw3d();
}

for (const ref of refs) {
  const label = ref + " · " + data.parts[ref].value;
  $("#part").append(element("option", label, { value: ref }));
}
$("#part").addEventListener("change", event => {
  const ref = event.target.value;
  if (view === "sch") frame(ref);
  else {
    choose(ref);
    if (view === "pcb") setSide(data.parts[ref].side);
  }
});
for (const button of all("[data-view]")) button.addEventListener("click", () => setView(button.dataset.view));
for (const button of all("[data-sheet]")) button.addEventListener("click", () => frame(button.dataset.sheet));
for (const layer of data.layers) {
  const button = element("button", layerLabels[layer], { type: "button", "data-side": layer });
  button.addEventListener("click", () => setSide(layer));
  $("#layer-buttons").append(button);
}
for (const button of all("[data-camera]")) button.addEventListener("click", () => orient3d(button.dataset.camera));
for (const checkbox of [$("#copper-toggle"), $("#silk-toggle"), $("#ref-toggle")]) checkbox.addEventListener("change", showBoard);
function zoom(factor) {
  if (view === "model" && three) {
    three.camera.position.sub(three.controls.target).multiplyScalar(factor).add(three.controls.target);
    three.controls.update();
  } else if (view !== "model") zoomSvg(view === "sch" ? sch : pcb, factor);
}
$("#zoom-in").addEventListener("click", () => zoom(.80));
$("#zoom-out").addEventListener("click", () => zoom(1.25));
$("#fit").addEventListener("click", () => {
  if (view === "model") orient3d("iso");
  else if (view === "sch") setBox(sch, schBox);
  else setBox(pcb, initialBoard);
});
$("#inspect-fuse").addEventListener("click", () => {
  setView("pcb");
  setSide("B");
  choose("F1");
  const [x, y] = data.parts.F1.xy;
  setBox(pcb, [px(x) - 14, py(y) - 12, 29, 22]);
});
$("#limits").append(table(["항목", data.hubRevision, "JLCPCB 공개 조건"], limits));
$("#order-stack").textContent = `시제품 2장 · ${data.layers.length}층 FR-4 · 1.6 mm · ${copperWeight} · 녹색 · 무연 HASL`;
$("#order-hand").textContent = `밑면 ${data.pcbaCount}개를 공장에서 실장하고 윗면 ${refs.filter(ref => data.parts[ref].populate === "YES" && !data.parts[ref].jlc).length}개는 직접 납땜합니다.`;
$("#order-orientation").textContent = "BOM과 CPL을 올리고, JLCPCB 밑면 미리보기에서 각 칩의 몸체 점을 오른쪽 그림의 1번 핀에 맞춥니다."
  + (fourLayer ? " U2의 방향은 U1·U3와 따로 확인합니다." : "");
$("#solder-access").textContent = fourLayer
  ? "손납땜 패드와 밑면 실장 부품 사이는 최소 2.05 mm입니다. JST PH에는 1.2–1.6 mm 평팁, XT30 전원 핀·퓨즈 홀더·C1 음극에는 열 회복이 빠른 인두와 2.4 mm 안팎의 평팁을 사용합니다."
  : "F1과 밑면 U1·U2 사이의 동박 간격은 0.26–0.27 mm입니다. 열린 쪽에서 작은 평팁을 댑니다.";
$("#bom").append(table(["위치", "규격", "조달·실장", "비고"], refs.map(ref => {
  const part = data.parts[ref];
  const supplier = part.jlc
    ? element("a", part.jlc + " · 밑면", { href: part.jlc === "C861498"
      ? "https://www.lcsc.com/product-detail/C861498.html" : `https://jlcpcb.com/partdetail/${part.jlc}` })
    : part.populate === "NATIVE" ? "기판 형상" : "윗면 수납땜";
  const jump = element("button", ref, { type: "button" });
  jump.addEventListener("click", () => { choose(ref); setView("pcb"); setSide(part.side); });
  return [jump, part.mpn, supplier, part.notes];
})));
const downloadNames = ["Gerber·드릴", "JLCPCB BOM", "JLCPCB CPL", "밑면 스텐실", "전체 BOM", "KiCad 프로젝트"];
for (const [index, [name, bytes]] of Object.entries(data.downloads).entries()) {
  const url = "data:application/octet-stream;base64," + bytes;
  $("#downloads").append(element("a", downloadNames[index], { href: url, download: name }));
}
$("#placement-image").src = "data:image/svg+xml;base64," + data.placementImage;
$("#provenance").textContent = `KiCad ${data.toolVersion} · ERC·DRC·회로도 대조 통과 · PCB ${Object.values(data.sha)[0].slice(0, 12)}`;
choose("J1");
setView("sch");
