// Compress the viewer model without simplifying it: meshopt-encoded, 16-bit positions.
// The CAD tessellation from build_b19_viewer.py stays intact (no decimation here).
//   node web/b19/compress_model.mjs <assets-dir>
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join } from 'node:path';
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { meshopt } from '@gltf-transform/functions';
import { MeshoptEncoder } from 'meshoptimizer';

const folder = process.argv[2];
if (!folder) throw new Error('usage: compress_model.mjs <assets-dir>');
const model = join(folder, 'model.glb');
const stepsPath = join(folder, 'steps.json');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const raw = readFileSync(model);
const steps = JSON.parse(readFileSync(stepsPath, 'utf8'));
if (steps.modelSha256 !== sha(raw)) throw new Error('steps.json does not describe this model.glb (already compressed?)');

await MeshoptEncoder.ready;
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.encoder': MeshoptEncoder });
const doc = await io.readBinary(raw);
await doc.transform(meshopt({ encoder: MeshoptEncoder, level: 'medium', quantizePosition: 16, quantizeNormal: 10 }));
const packed = await io.writeBinary(doc);
writeFileSync(model + '.tmp', packed);
renameSync(model + '.tmp', model);
steps.rawModelSha256 = steps.modelSha256;
steps.modelSha256 = sha(packed);
steps.modelEncoding = 'EXT_meshopt_compression, KHR_mesh_quantization (16-bit positions)';
writeFileSync(stepsPath, JSON.stringify(steps));
console.log(`model ${(raw.length / 1e6).toFixed(1)} MB -> ${(packed.length / 1e6).toFixed(1)} MB`);
