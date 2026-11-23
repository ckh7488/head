import { cp, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { harnesses } from "./diagram/connections.js";

const here = dirname(fileURLToPath(import.meta.url));

export async function packageDiagram(output, revision) {
  if (!/^[0-9a-f]{40}$/.test(revision ?? "")) {
    throw new Error("The diagram needs a full source commit SHA.");
  }
  const cutList = await readFile(resolve(here, "../../mechanical/WIRING-CUT-LIST.csv"), "utf8");
  const [, ...lines] = cutList.trim().split(/\r?\n/);
  const wires = Object.fromEntries(lines.map(line => {
    const fields = line.split(",");
    const [id, circuit, gauge, color, from, to, path, cut, note] = fields;
    if (fields.length !== 9 || !/^W\d+$/.test(id)) {
      throw new Error(`Invalid wiring cut list row: ${line}`);
    }
    return [id, { circuit, gauge, color, from, to, path, cut, note }];
  }));
  const used = new Set(harnesses.flatMap(harness => harness.rows.map(row => row.wire)).filter(Boolean));
  if (Object.keys(wires).length !== lines.length || used.size !== lines.length ||
      [...used].some(id => !Object.hasOwn(wires, id))) {
    throw new Error("The diagram and wiring cut list must include the same wire IDs.");
  }

  const source = join(here, "diagram");
  const docs = `https://github.com/ckh7488/head/blob/${revision}/`;
  const html = (await readFile(join(source, "index.html"), "utf8"))
    .replace(/data-doc="([^"]+)"/g, (_, path) => `href="${docs}${path}"`);
  await mkdir(output, { recursive: true });
  await Promise.all([
    ...["diagram.css", "diagram.js", "connections.js", "images"].map(name =>
      cp(join(source, name), join(output, name), { recursive: true })),
    writeFile(join(output, "index.html"), html),
    writeFile(join(output, "wires.js"), `export const wires = ${JSON.stringify(wires)};\n`),
    writeFile(join(output, "WIRING-CUT-LIST.csv"), cutList),
  ]);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [output, revision] = process.argv.slice(2);
  if (!output) throw new Error("Usage: package_diagram.mjs OUTPUT_DIRECTORY SOURCE_GIT_SHA");
  await packageDiagram(output, revision);
}
