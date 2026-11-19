import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

const cadPath = process.argv[2] ?? "mechanical/R5-B15-Assembly.FCStd";
const root = resolve(process.argv[3] ?? "web");
const read = path => readFile(resolve(root, path));
const json = async path => JSON.parse(await read(path));
const cadHash = createHash("sha256").update(await readFile(cadPath)).digest("hex");
const [assembly, wiring, connectors, review] = await Promise.all([
  json("assets/assembly.json"),
  json("assets/wiring.json"),
  json("assets/connectors.json"),
  json("assembly/interference.json"),
]);
for (const [name, data] of Object.entries({ assembly, wiring, connectors, review })) {
  assert.equal(data.cad_sha256, cadHash, name + " is from a different CAD version");
}

const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
async function verifyNodes(path, names) {
  const bytes = await read(path);
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const { scene } = await loader.parseAsync(buffer, "");
  for (const name of names) assert.ok(scene.getObjectByName(name), path + " lacks " + name);
}
await Promise.all([
  verifyNodes("assets/assembly.glb", assembly.parts.map(part => part.name)),
  verifyNodes("assets/connectors.glb", Object.keys(connectors.parts)),
  ...(Object.keys(review.stops).length ? [
    verifyNodes("assembly/interference.glb", Object.values(review.stops).flatMap(stop => stop.nodes)),
  ] : []),
]);
console.log(`Loaded ${assembly.parts.length} CAD nodes and ${Object.keys(connectors.parts).length} connectors at ${cadHash.slice(0, 12)}.`);
