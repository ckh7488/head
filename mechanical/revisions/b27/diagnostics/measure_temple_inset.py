"""Screen the 3 mm target-surface allowance over the fixed motion samples."""
from argparse import ArgumentParser
import json
from pathlib import Path

import numpy as np
import trimesh as tr
from trimesh.ray.ray_pyembree import RayMeshIntersector

from check_b27_skull_cover import Export, ROOT, SPEC, angle_grid, in_zone, poses_for


MECHANISM = ('Part019', 'Part024', 'Part025', 'Part026', 'Part027', 'Part028', 'Part044',
             'EyePitchLinkCradlePin', 'EyePitchLinkHornPin', 'Part057', 'Part060',
             'EyePitchBearingL', 'EyePitchBearingR', 'CradleMountFrameL', 'CradleMountFrameR')


def screen(cad, out):
    export = Export(cad)
    spec = json.loads(SPEC.read_bytes())
    fixed_grid = angle_grid(export, spec)
    rows = {}
    for side, label in ((-1, 'left'), (1, 'right')):
        surfaces = [tr.load_mesh(ROOT/spec['anatomy'][kind][label])
                    for kind in ('cranium', 'temple_fill')]
        cast = RayMeshIntersector(tr.util.concatenate(surfaces))
        side_rows = rows[label] = {}
        for part in MECHANISM:
            mesh = export.mesh(part)
            samples, _ = tr.sample.sample_surface_even(mesh, max(800, int(mesh.area*4)), seed=17)
            seen, without, peak = 0, 0, []
            above, vertices = 0, []
            for transform in poses_for(export.motion[part], fixed_grid, export.layout):
                points = tr.transform_points(samples, transform)
                points = points[in_zone(points,spec,side)]
                if not len(points):
                    continue
                source = points.copy()
                source[:,0] = side*100.
                direction = np.broadcast_to([-side, 0., 0.], source.shape)
                hit, ri, _ = cast.intersects_location(source, direction, multiple_hits=False)
                excess = 3.0 - (hit[:,0]-points[ri,0])*side
                seen += len(points)
                without += len(points)-len(ri)
                above += int((excess > 0.).sum())
                peak.extend(excess.tolist())
                if len(ri):
                    worst = int(excess.argmax())
                    vertices.append((float(excess[worst]),points[ri[worst]].round(4).tolist()))
            if seen:
                row = {'samples':seen,'without_reference_ray':without,'closer_than_3mm':above}
                if peak:
                    row.update(excess_p98_mm=round(float(np.percentile(peak,98)),4),
                               excess_max_mm=round(max(peak),4), worst_sample_mm=max(vertices)[1])
                side_rows[part] = row
                print(label, part, row, flush=True)
    out.write_text(json.dumps(rows, indent=2)+'\n', encoding='utf-8')


if __name__=='__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('out', type=Path)
    screen(**vars(parser.parse_args()))
