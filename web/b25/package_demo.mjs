import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const [target] = process.argv.slice(2);
if (!target) throw new Error("Usage: node web/b25/package_demo.mjs OUTPUT");
const output = resolve(target);

const sources = [
  "app.js", "motion.js", "styles.css", "viewer.js", "wiring.js",
  "assets/noto-sans-cjk-license.txt", "assets/review-bold.woff", "assets/review-regular.woff",
  "assets/tracking-test.mp4", "assets/b25-motion/assembly.glb", "assets/b25-motion/assembly.json",
  "assets/b25-motion/assembly-poster.webp",
];
const vendor = ["build/three.module.min.js", "build/three.core.min.js", "LICENSE",
  "examples/jsm/controls/OrbitControls.js", "examples/jsm/loaders/GLTFLoader.js",
  "examples/jsm/utils/BufferGeometryUtils.js", "examples/jsm/libs/meshopt_decoder.module.js"];

async function copy(from, to) {
  const file = join(output, to);
  await mkdir(dirname(file), { recursive: true });
  await copyFile(join(web, from), file);
}

await Promise.all([
  ...sources.map(path => copy(path, path)),
  ...vendor.map(path => copy(`node_modules/three/${path}`, `vendor/three/${path}`)),
]);
const html = (await readFile(join(web, "index.html"), "utf8"))
  .replaceAll("./node_modules/three/", "./vendor/three/")
  .replace("/three.module.js", "/three.module.min.js");
await writeFile(join(output, "index.html"), html);
