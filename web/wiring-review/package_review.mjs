import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const [cadDir, resultDir, bundle, output, beforeDir, beforeCadDir, cadFile] = process.argv.slice(2);
if (!output || Boolean(beforeDir) !== Boolean(beforeCadDir)) {
  throw new Error("Usage: package_review.mjs CAD_DATA RESULT_DIR BUNDLED_JS OUTPUT_HTML [BEFORE_RESULT_DIR BEFORE_CAD_DATA [CAD_FILE]]");
}
const root = fileURLToPath(new URL("../../", import.meta.url));
const here = fileURLToPath(new URL("./", import.meta.url));
const read = path => readFile(path);
const string = async path => (await read(path)).toString("utf8");
const json = async path => JSON.parse(await string(path));
const base64 = async path => (await read(path)).toString("base64");
const optionalJson = async (path, fallback) => {
  try { return await json(path); }
  catch (error) { if (error.code === "ENOENT") return fallback; throw error; }
};
const report = await json(join(resultDir, "wiring-check.json"));
const cad = await read(cadFile ?? join(root, "mechanical", "R5-B16-Wiring.FCStd"));
if (report.cad_sha256 !== createHash("sha256").update(cad).digest("hex")) {
  throw new Error("The check results and B16 CAD file have different revisions.");
}
const ids = ["Part000", "Part007", "CableSaddle"];
const wiring = await json(join(root, "web/assets/wiring.json"));
const data = {
  report,
  frames: await json(join(resultDir, "wiring-frames.json")),
  hardware: await json(join(cadDir, "hardware.json")),
  assembly: await json(join(root, "web/assets/assembly.json")),
  wiring: { blocks: await optionalJson(join(cadDir, "wiring-blocks.json"), wiring.blocks) },
  model: await base64(join(root, "web/assets/assembly.glb")),
  meshes: Object.fromEntries(await Promise.all(ids.map(async id => [
    id, await base64(join(cadDir, "world", id + ".stl")),
  ]))),
};
if (beforeDir) {
  const before = await json(join(beforeDir, "wiring-check.json"));
  const beforeLayout = await json(join(beforeCadDir, "cad_parts.json"));
  if (before.cad_sha256 !== beforeLayout.source_sha256) {
    throw new Error("The original check results and CAD export have different revisions.");
  }
  const frames = await json(join(beforeDir, "wiring-frames.json"));
  const keys = new Set(frames.map(frame => frame.pose.join(",")));
  if (keys.size !== data.frames.length || !data.frames.every(frame => keys.has(frame.pose.join(",")))) {
    throw new Error("The comparison requires the same checked poses in both models.");
  }
  const beforeMeshes = await Promise.all(ids.map(async id => [
    id, await base64(join(beforeCadDir, "world", id + ".stl")),
  ]));
  data.before = {
    report: before,
    frames,
    meshes: Object.fromEntries(beforeMeshes.filter(([id, value]) => value !== data.meshes[id])),
    blocks: await optionalJson(join(beforeCadDir, "wiring-blocks.json"), wiring.blocks),
  };
}
const css = await string(join(here, "review.css"));
const js = (await string(bundle)).replaceAll("</script", "<\\/script");
const payload = gzipSync(JSON.stringify(data)).toString("base64");
const html = (await string(join(here, "index.html")))
  .replace('  <link rel="stylesheet" href="./review.css">', () => "<style>" + css + "</style>")
  .replace(/ *<script type="importmap">.*<\/script>\r?\n/, "")
  .replace('  <script type="module" src="./review.js"></script>', () =>
    '<script id="review-payload" type="application/octet-stream" data-encoding="gzip-base64">' + payload + "</script>\n" +
    "<script>" + js + "</script>");
await writeFile(output, html, "utf8");
console.log("Wrote " + output + " with " + data.frames.length + " checked poses.");
