function ids(list) {
  return list.trim().split(/\s+/).filter(Boolean);
}

export function withAssemblyState(definitions, joints, hardware) {
  const parents = new Map();
  const children = new Map();
  const stages = definitions.map(step => {
    const explicitMoves = new Set(step.moves.flatMap(move => move.ids));
    const placed = new Set();
    function gather(id, group, out) {
      if (placed.has(id) || (explicitMoves.has(id) && !group.has(id))) return;
      placed.add(id);
      out.push(id);
      for (const child of children.get(id) || []) gather(child, group, out);
    }

    const moves = step.moves.map(move => {
      const expanded = [];
      const group = new Set(move.ids);
      for (const id of group) gather(id, group, expanded);
      return { ...move, ids: expanded };
    });
    const fixed = [];
    const fixtures = ids(step.base);
    function root(id) {
      while (parents.has(id)) id = parents.get(id);
      return id;
    }
    const stations = new Set(fixtures.map(root));
    for (const id of ["Part000", "Part010"]) {
      if (stations.has(id)) fixtures.unshift(id);
    }
    const stationary = new Set();
    for (const id of fixtures) gather(id, stationary, fixed);
    const assembled = { ...step, moves, base: fixed.join(" ") };

    for (const [parent, list] of joints[step.id] || []) {
      if (!placed.has(parent)) throw Error(`${step.id} does not contain join parent ${parent}`);
      for (const child of ids(list)) {
        if (!placed.has(child) || parents.has(child) || root(parent) === child) {
          throw Error(`${step.id} cannot attach ${child} to ${parent}`);
        }
        if (!children.has(parent)) children.set(parent, []);
        children.get(parent).push(child);
        parents.set(child, parent);
      }
    }
    return assembled;
  });
  for (const item of hardware) {
    if (!item.tool && !parents.has(item.id)) throw Error(`Missing installation stage for ${item.id}`);
  }
  return stages;
}
