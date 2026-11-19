import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

const vector = xyz => new THREE.Vector3(...xyz);
const up = new THREE.Vector3(0, 0, 1);
const sky = new THREE.Color(0x85ddd1);
const fixedTint = new THREE.Color(0xafb9bd);
const gold = new THREE.MeshStandardMaterial({ color: 0xecae63, metalness: .32, roughness: .49 });
const toolColor = new THREE.MeshStandardMaterial({ color: 0xffca6e, transparent: true, opacity: .55, depthWrite: false });

function ring(outer, inner, depth, sides, innerSides, phase = 0) {
  const polygon = (radius, n, target, angle = 0) => {
    for (let i = 0; i < n; i++) {
      const theta = angle + 2 * Math.PI * i / n;
      target[i ? "lineTo" : "moveTo"](radius * Math.cos(theta), radius * Math.sin(theta));
    }
    target.closePath();
    return target;
  };
  const outline = polygon(outer, sides, new THREE.Shape(), phase);
  outline.holes.push(polygon(inner, innerSides, new THREE.Path()));
  return new THREE.ExtrudeGeometry(outline, { depth, bevelEnabled: false, curveSegments: 1 });
}

function fastener(part) {
  const { seat, axis, type, size, length, phase } = part;
  const node = new THREE.Group();
  node.position.copy(vector(seat));
  if (type === "spanner") {
    const outline = new THREE.Shape(part.profile.map(point => new THREE.Vector2(...point)));
    const shape = new THREE.ExtrudeGeometry(outline, { depth: part.thickness, bevelEnabled: false });
    const normal = vector(axis);
    const handle = vector(part.outward);
    shape.applyMatrix4(new THREE.Matrix4().makeBasis(handle.clone().cross(normal), handle, normal));
    const material = toolColor.clone();
    material.color.set(0x83e8ce);
    node.add(new THREE.Mesh(shape, material));
    return { node, label: size === 3 ? "5.5 mm 오픈 스패너" : "4 mm 오픈 스패너", materials: [material], kind: "fastener" };
  }
  node.quaternion.setFromUnitVectors(up, vector(axis));
  const material = (part.tool ? toolColor : gold).clone();
  const radius = size / 2;
  const isSmall = size === 2;
  const add = (geometry, elevation, verticalCylinder = true) => {
    const shape = new THREE.Mesh(geometry, material);
    if (verticalCylinder) shape.rotation.x = Math.PI / 2;
    shape.position.z = elevation;
    node.add(shape);
  };

  if (type === "nut") {
    const across = isSmall ? 4 : 5.5;
    add(ring(across / Math.sqrt(3), radius, isSmall ? 1.6 : 2.4, 6, 24, phase), 0, false);
  } else if (type === "washer") {
    add(ring(isSmall ? 2.5 : 3.5, isSmall ? 1.1 : 1.6, isSmall ? .3 : .5, 30, 24), 0, false);
  } else if (type === "socket") {
    material.color.set(0x83e8ce);
    add(ring(part.radius, part.opening, part.depth, 36, 30), 0, false);
    add(new THREE.CylinderGeometry(part.radius, part.radius, length - part.depth, 36), (length + part.depth) / 2);
  } else if (type === "tool") {
    add(new THREE.CylinderGeometry(part.radius, part.radius, length, 6), length / 2);
  } else {
    const height = isSmall ? 2 : 3;
    const head = isSmall ? 1.93 : 2.78;
    const recess = (isSmall ? 1.5 : 2.5) / Math.sqrt(3);
    if (type !== "head") add(new THREE.CylinderGeometry(radius, radius, length, 24), length / 2);
    add(new THREE.CylinderGeometry(head, head, height / 2, 30), -height / 4);
    add(ring(head, recess, height / 2, 30, 6), -height, false);
  }

  const labels = { nut: `M${size} 일반 육각너트`, washer: `M${size} 평와셔`, socket: "5.5 mm 소켓",
    tool: "2.5 mm 육각렌치", head: `M${size} 육각렌치 원통머리 외형` };
  const label = labels[type] || `M${size}×${length} 육각렌치 원통머리`;
  return { node, label, materials: [material], kind: "fastener" };
}

function keyLight(scene, color, intensity, position) {
  const light = new THREE.DirectionalLight(color, intensity);
  light.position.set(...position);
  scene.add(light);
}

export class WalkthroughScene {
  constructor(host, onPick) {
    this.host = host;
    this.onPick = onPick;
    this.entries = new Map();
    this.overlapNodes = new Map();
    this.paths = new THREE.Group();
    this.scene = new THREE.Scene();
    this.scene.add(this.paths);
    this.camera = new THREE.OrthographicCamera(-100, 100, 100, -100, .5, 1800);
    this.camera.up.copy(up);
    this.camera.position.set(210, -250, 180);
    this.renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    this.renderer.setClearAlpha(0);
    this.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.65));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.18;
    this.renderer.localClippingEnabled = true;
    this.renderer.domElement.setAttribute("aria-label", "B14 움직이는 CAD 형상");
    this.host.append(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.minZoom = .35;
    this.controls.maxZoom = 8;
    this.controls.addEventListener("change", () => this.schedule());
    this.renderer.domElement.addEventListener("pointerdown", event => {
      this.pointerDown = [event.clientX, event.clientY];
    });
    this.renderer.domElement.addEventListener("pointerup", event => this.pick(event));

    this.scene.add(new THREE.HemisphereLight(0xdcecfb, 0x64646b, 1.56));
    keyLight(this.scene, 0xffe9d1, 2.45, [85, -170, 245]);
    keyLight(this.scene, 0xaad3ff, 1.7, [-105, 190, 160]);
    keyLight(this.scene, 0xefffff, .66, [177, 81, -151]);

    const observer = new ResizeObserver(() => this.resize());
    observer.observe(host);
    this.resize();
  }

  async load(hardware, steps) {
    const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
    const json = async url => {
      const result = await fetch(url);
      if (!result.ok) throw Error(url + " · " + result.status);
      return result.json();
    };
    const [data, cad, audit] = await Promise.all([
      json("../assets/assembly.json"), loader.loadAsync("../assets/assembly.glb"),
      json("./interference.json"),
    ]);
    if (audit.cad_sha256 !== data.cad_sha256) throw Error("CAD and measurements have different revisions");
    this.scene.add(cad.scene);
    for (const part of data.parts) {
      const node = cad.scene.getObjectByName(part.name);
      if (!node) throw Error(`Missing CAD part ${part.cad_id}`);
      this.register(part.cad_id, { node, label: part.label, center: new THREE.Box3(...part.bounds.map(vector)).getCenter(new THREE.Vector3()) });
    }
    for (const part of hardware) {
      const entry = fastener(part);
      entry.center = vector(part.seat);
      this.scene.add(entry.node);
      this.register(part.id, entry);
    }
    const overlay = Object.keys(audit.stops).length ? (await loader.loadAsync("./interference.glb")).scene : null;
    if (overlay) this.scene.add(overlay);
    for (const [id, data] of Object.entries(audit.stops)) {
      const nodes = data.nodes.map(name => {
        const node = overlay.getObjectByName(name);
        if (!node) throw Error(`Missing interference solid ${name}`);
        node.visible = false;
        node.traverse(mesh => {
          if (!mesh.isMesh) return;
          mesh.material = new THREE.MeshBasicMaterial({ color: 0xff5750, depthTest: false, depthWrite: false, toneMapped: false });
          mesh.renderOrder = 9;
        });
        return node;
      });
      this.overlapNodes.set(id, nodes);
    }
    for (const step of steps) {
      const all = [...step.base.split(" "), ...step.moves.flatMap(move => move.ids)];
      for (const id of all) if (!this.entries.has(id)) throw Error(`Unknown assembly part ${id} in ${step.id}`);
      if (step.blocker && !this.overlapNodes.has(step.id)) throw Error(`Missing measured stop ${step.id}`);
    }
    return audit.stops;
  }

  register(id, entry) {
    const materials = entry.materials || [];
    if (!entry.materials) {
      entry.node.traverse(mesh => {
        if (!mesh.isMesh) return;
        mesh.material = mesh.material.clone();
        materials.push(mesh.material);
      });
    }
    entry.original = entry.node.position.clone();
    entry.initial = entry.original.clone();
    entry.orientation = entry.node.quaternion.clone();
    entry.materials = materials.map(material => ({ material, color: material.color.clone(), opacity: material.opacity }));
    entry.node.userData.assemblyPart = id;
    entry.node.visible = false;
    this.entries.set(id, entry);
  }

  show(step) {
    this.step = step;
    const hinge = vector([0, -39, 119]);
    const closed = new THREE.Quaternion().setFromAxisAngle(vector([1, 0, 0]), Math.PI / 2);
    for (const [id, { node, original, initial, orientation }] of this.entries) {
      initial.copy(original);
      node.quaternion.copy(orientation);
      if (step.closedLids && (id === "Part078" || id === "Part079")) {
        initial.sub(hinge).applyQuaternion(closed).add(hinge);
        node.quaternion.premultiply(closed);
      }
      if (step.seatOffsets?.[id]) initial.add(vector(step.seatOffsets[id]));
      node.position.copy(initial);
    }
    this.moveById = new Map(step.moves.flatMap(({ ids, offset }) => ids.map(id => [id, vector(offset)])));
    this.fixed = new Set(step.base.split(" "));
    for (const arrow of this.paths.children.slice()) {
      this.paths.remove(arrow);
      arrow.line.material.dispose();
      arrow.cone.material.dispose();
    }
    for (const move of step.moves.slice(0, 4)) {
      const offset = vector(move.offset);
      const length = offset.length();
      const entry = this.entries.get(move.ids[0]);
      const start = entry.center.clone().add(entry.initial).sub(entry.original).add(offset);
      const arrow = new THREE.ArrowHelper(offset.normalize().negate(), start, length, 0x9de6e1, Math.min(3.5, length * .35), Math.min(2.4, length * .28));
      arrow.traverse(line => {
        if (!line.material) return;
        line.material.depthWrite = false;
        line.material.depthTest = false;
        line.material.transparent = true;
        line.material.opacity = .64;
        line.renderOrder = 6;
      });
      this.paths.add(arrow);
    }
    this.resetView();
  }

  resetView() {
    if (!this.step) return;
    const target = vector(this.step.focus);
    const position = vector(this.step.view).normalize().multiplyScalar(300);
    this.controls.target.copy(target);
    this.camera.position.copy(target.add(position));
    this.camera.zoom = 1;
    this.controls.update();
    this.resize();
  }

  applyStyle({ ghost, section }) {
    const { cut, view } = this.step;
    let planes = [];
    if (cut && section) {
      const [axis, offset] = cut;
      const normal = new THREE.Vector3();
      normal[axis] = -Math.sign(view["xyz".indexOf(axis)]);
      planes = [new THREE.Plane(normal, -normal[axis] * offset)];
    }
    this.planes = planes;
    for (const [id, entry] of this.entries) {
      const isMoving = this.moveById.has(id);
      entry.node.visible = this.fixed.has(id) || isMoving;
      if (!entry.node.visible) continue;
      const translucent = ghost && entry.kind !== "fastener";
      for (const { material, color, opacity } of entry.materials) {
        material.clippingPlanes = planes;
        material.opacity = translucent ? (isMoving ? .42 : .19) : opacity;
        material.transparent = translucent || opacity < 1;
        material.depthWrite = !material.transparent;
        material.color.copy(color);
        if (!entry.kind) material.color.lerp(isMoving ? sky : fixedTint, isMoving ? .62 : .20);
        material.needsUpdate = true;
      }
    }
    this.schedule();
  }

  setPosition(position, showHit) {
    for (const [id, offset] of this.moveById) {
      const entry = this.entries.get(id);
      entry.node.position.copy(entry.initial).addScaledVector(offset, 1 - position);
    }
    for (const [id, nodes] of this.overlapNodes) {
      for (const node of nodes) node.visible = id === this.step.id && showHit;
    }
    this.schedule();
  }

  resize() {
    const width = Math.max(1, this.host.clientWidth);
    const height = Math.max(1, this.host.clientHeight);
    const aspect = width / height;
    const halfHeight = (this.step?.span || 150) / (2 * Math.min(1, aspect));
    this.camera.left = -halfHeight * aspect;
    this.camera.right = -this.camera.left;
    this.camera.top = halfHeight;
    this.camera.bottom = -halfHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
    this.schedule();
  }

  schedule() {
    if (this.scheduled) return;
    this.scheduled = requestAnimationFrame(() => {
      this.scheduled = null;
      this.renderer.render(this.scene, this.camera);
    });
  }

  pick(event) {
    if (!this.pointerDown || event.button !== 0 ||
        Math.hypot(event.clientX - this.pointerDown[0], event.clientY - this.pointerDown[1]) > 5) return;
    const bounds = this.renderer.domElement.getBoundingClientRect();
    const pointer = new THREE.Vector2((event.clientX - bounds.x) / bounds.width * 2 - 1, 1 - (event.clientY - bounds.y) / bounds.height * 2);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(pointer, this.camera);
    const visible = [...this.entries.values()].filter(item => item.node.visible).map(item => item.node);
    const hit = ray.intersectObjects(visible, true).find(({ point }) => this.planes.every(plane => plane.distanceToPoint(point) >= 0));
    let object = hit?.object;
    while (object && !object.userData.assemblyPart) object = object.parent;
    this.onPick(object ? this.entries.get(object.userData.assemblyPart).label : "");
  }
}
