import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";
import { partGroups } from "./catalog.js";
import { packageDiagram } from "./package_diagram.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
const [cadDir, posesFile, output, revision, three = join(root, "web/node_modules/three")] = process.argv.slice(2);
if (!output || !/^[0-9a-f]{40}$/.test(revision ?? "")) {
  throw new Error("Usage: package_review.mjs CAD_DIR POSE_DATA_JSON HOST_DIRECTORY SOURCE_GIT_SHA [THREE_DIRECTORY]");
}
const digest = bytes => createHash("sha256").update(bytes).digest("hex");
const readJson = async path => JSON.parse(await readFile(path, "utf8"));
const layout = await readJson(join(cadDir, "cad_parts.json"));
const poses = await readJson(posesFile);
const assembly = await readFile(join(root, "mechanical/revisions/b25/R5-B25-Assembly.FCStd"));
if (poses.cad !== layout.source_sha256 || poses.cad !== digest(assembly)) {
  throw new Error("The pose data, exported mesh index and current B25 assembly must match.");
}
const partIds = [...new Set(Object.values(partGroups).flat())];
const vendor = {
  "three.module.min.js": "build/three.module.min.js",
  "three.core.min.js": "build/three.core.min.js",
  "controls/OrbitControls.js": "examples/jsm/controls/OrbitControls.js",
  "loaders/STLLoader.js": "examples/jsm/loaders/STLLoader.js",
  "LICENSE.txt": "LICENSE",
};
await Promise.all(["assets", "vendor/controls", "vendor/loaders"].map(dir => mkdir(join(output, dir), { recursive: true })));
await Promise.all(Object.entries(vendor).map(([to, from]) => copyFile(join(three, from), join(output, "vendor", to))));
for (const id of partIds) {
  const bytes = await readFile(join(cadDir, "world", id + ".stl"));
  if (digest(bytes) !== layout.world_sha256[id]) throw new Error(`${id} does not match the CAD export.`);
  await writeFile(join(output, "assets", id + ".stlz"), gzipSync(bytes));
}
const docs = `https://github.com/ckh7488/head/blob/${revision}/`;
const html = (await readFile(join(here, "index.html"), "utf8"))
  .replace(/data-doc="([^"]+)"/g, (_, path) => `href="${docs}${path}"`);
await Promise.all([
  packageDiagram(join(output, "diagram"), revision),
  writeFile(join(output, "index.html"), html),
  copyFile(join(here, "catalog.js"), join(output, "catalog.js")),
  copyFile(join(here, "review.js"), join(output, "review.js")),
  copyFile(join(here, "review.css"), join(output, "review.css")),
  writeFile(join(output, "assets", "poses.json"), JSON.stringify({
    ...poses, revision, motion: Object.fromEntries(partIds.map(id => [id, layout.world_motion[id]])),
  })),
]);
console.log(`Wrote ${partIds.length} B25 CAD meshes and ${poses.service.length} service poses to ${output}.`);
