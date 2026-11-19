import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

const vector = xyz => new THREE.Vector3(...xyz);
const up = new THREE.Vector3(0, 0, 1);
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

export function fastener(part) {
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
  if (node.children.length > 1) {
    const pieces = node.children.map(mesh => {
      mesh.updateMatrix();
      const geometry = mesh.geometry.index ? mesh.geometry.toNonIndexed() : mesh.geometry;
      return geometry.applyMatrix4(mesh.matrix);
    });
    const geometry = mergeGeometries(pieces);
    for (const child of node.children) child.geometry.dispose();
    for (const piece of pieces) piece.dispose();
    node.clear();
    node.add(new THREE.Mesh(geometry, material));
  }
  return { node, label, materials: [material], kind: "fastener" };
}
