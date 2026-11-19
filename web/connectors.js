import catalog from "./assets/connectors.json" with { type: "json" };

export const connectorInfo = catalog.parts;

export async function loadConnectors(loader, base, cadHash) {
  if (catalog.cad_sha256 !== cadHash) throw Error("Connector placements and assembly have different revisions");
  const { scene } = await loader.loadAsync(new URL("connectors.glb", base).href);
  return new Map(Object.keys(connectorInfo).map(id => {
    const node = scene.getObjectByName(id);
    if (!node) throw Error(`Missing connector ${id}`);
    return [id, node];
  }));
}

export function useConnector(original, replacement) {
  if (!replacement) return original;
  const parent = original.parent;
  replacement.name = original.name;
  original.removeFromParent();
  parent.add(replacement);
  return replacement;
}
