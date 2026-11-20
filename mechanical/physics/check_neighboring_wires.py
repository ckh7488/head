"""Compare fixed-length and reference routes, and report overlap within the references."""
from argparse import ArgumentParser
from itertools import combinations
import json
from pathlib import Path

import numpy as np

from wiring_check import Cable, ROOT, read, reference_cables, segment_gap
from wiring_motion import matrices


def compare(cad, result):
    layout = read(cad/'cad_parts.json')
    rows = read(result/'wiring-check.json')
    if rows['cad_sha256'] != layout['source_sha256']:
        raise ValueError('CAD and wire frames need to share the same revision')
    frames = read(result/'wiring-frames.json')
    wiring = read(ROOT/'web/assets/wiring.json')
    for record, frame in zip(rows['records'], frames, strict=True):
        if record['pose'] != frame['pose']:
            raise ValueError('The report and frame sequence differ')
        transforms = matrices(layout, *record['pose'])
        revised = [Cable(p['id'], np.asarray(p['points']), p['d'], record['lengths'][p['id']]['length_mm'], 0.)
                   for p in frame['paths']]
        neighbors = reference_cables(wiring, transforms, revised)
        record['reference_pairs'] = [hit for cable in revised for reference in neighbors
                                     if (hit := segment_gap(cable, reference))]
        record['neighbor_pairs'] = [hit for a, b in combinations(neighbors, 2)
                                    if (hit := segment_gap(a, b))]
        record['neighbor_lengths_mm'] = {c.name: round(float(c.arc[-1]), 3) for c in neighbors}
        frame['neighbors'] = [dict(id=c.name,d=c.diameter,points=c.points.round(3).tolist()) for c in neighbors]
    for name, value in [('wiring-check.json', rows), ('wiring-frames.json', frames)]:
        path = result/name
        staged = path.with_suffix('.pending')
        staged.write_text(json.dumps(value,separators=(',',':'))+'\n',encoding='utf-8')
        staged.replace(path)
    print(f"{len(frames)} poses compared with {len(frames[0]['neighbors'])} retained B15 route models.",flush=True)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad',type=Path)
    parser.add_argument('result',type=Path)
    compare(**vars(parser.parse_args()))
