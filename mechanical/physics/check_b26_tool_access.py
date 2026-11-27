"""Check that hand tools reach the visible B26 base nuts.

* Bottom-hatch nuts: none needed. Loose hex recesses on the bars stop them turning.
* Yaw bracket feet (assembly step 'yaw-bracket-feet'): a 5.5 mm nut driver or 1/4" socket,
  8.0 mm outside diameter, straight down onto the nut, against the parts installed at that step.
  The report also gives the widest socket (0.1 mm steps) that still reaches each nut.
  A horizontal open-end spanner does not fit between the bracket wall, the posts and the cup
  wall there (0 degrees free for a 100 mm spanner).

    python mechanical/physics/check_b26_tool_access.py build/b26/cad build/b26/assembly-assets/steps.json \
        mechanical/revisions/b26/tool-access.json
"""

from argparse import ArgumentParser
import json
from pathlib import Path

import manifold3d as md
import numpy as np
from shapely.geometry import Polygon
import trimesh

PROFILE = [(-5.75, -3), (-2.8, -3), (-2.8, 2.2), (2.8, 2.2), (2.8, -3), (5.75, -3),
           (5.75, 2.5), (2.6, 7), (2.6, 100), (-2.6, 100), (-2.6, 7), (-5.75, 2.5)]
SOCKET_OUTER_MM, SOCKET_LENGTH_MM = 8.0, 60.
THICKNESS = 2.5
MIN_SWING_DEG = 30.
HATCH_NUTS = {'hatchNut0': (-41.2, 51.), 'hatchNut1': (-41.2, 71.), 'hatchNut2': (41.2, 51.), 'hatchNut3': (41.2, 71.)}


def solid(mesh):
    return md.Manifold(md.Mesh(np.asarray(mesh.vertices, np.float32), np.asarray(mesh.faces, np.uint32)))


def spanner(centre, bottom, angle):
    outward = np.array([np.cos(angle), np.sin(angle), 0.])
    axis = np.array([0., 0., 1.])
    frame = np.eye(4)
    frame[:3, :3] = np.column_stack((np.cross(outward, axis), outward, axis))
    frame[:3, 3] = (centre[0] + outward[0], centre[1] + outward[1], bottom)
    model = trimesh.creation.extrude_polygon(Polygon(PROFILE), THICKNESS)
    return model.apply_transform(frame)


def windows(free, step):
    """Contiguous free angle ranges (degrees) on the circle."""
    n = len(free)
    if all(free):
        return [(0., 360.)]
    start = next(i for i in range(n) if not free[i])
    result, run = [], None
    for k in range(1, n + 1):
        i = (start + k) % n
        if free[i] and run is None:
            run = i
        if not free[i] and run is not None:
            result.append((run*step, ((i - 1) % n)*step))
            run = None
    return result


def width(window, step):
    a, b = window
    return (b - a) % 360 + step


class Scene:
    def __init__(self, cad):
        self.world = cad/'world'
        self.cache = {}

    def mesh(self, name):
        if name not in self.cache:
            path = self.world/f'{name}.stl'
            self.cache[name] = trimesh.load(path, force='mesh') if path.exists() else None
        return self.cache[name]

    def blocked(self, tool, parts):
        a, (lo, hi) = solid(tool), tool.bounds
        hit = {}
        for name in parts:
            mesh = self.mesh(name)
            if mesh is None or not len(mesh.faces):
                continue
            b = mesh.bounds
            if (b[0] > hi + .05).any() or (b[1] < lo - .05).any():
                continue
            volume = (a ^ solid(mesh)).volume()
            if volume > .01:
                hit[name] = round(volume, 3)
        return hit


def sweep(scene, centre, bottom, parts, step=5.):
    angles = np.arange(0., 360., step)
    hits = [scene.blocked(spanner(centre, bottom, np.radians(a)), parts) for a in angles]
    free = [not h for h in hits]
    found = windows(free, step)
    best = max(found, key=lambda w: width(w, step)) if found else None
    blockers = sorted({name for h in hits for name in h})
    return {'free_windows_deg': found, 'widest_deg': width(best, step) if best else 0.,
            'centre_deg': ((best[0] + width(best, step)/2 - step/2) % 360) if best else None,
            'pass': bool(best) and width(best, step) >= MIN_SWING_DEG, 'blocking_parts': blockers}


def insertion(scene, centre, bottom, angle_deg, parts, reach=60., step=1.):
    """Slide the spanner in along its own axis, from `reach` mm outside to the nut."""
    angle = np.radians(angle_deg)
    outward = np.array([np.cos(angle), np.sin(angle), 0.])
    hits = {}
    for d in np.arange(reach, -step/2, -step):
        tool = spanner(centre, bottom, angle).apply_translation(outward*d)
        for name, volume in scene.blocked(tool, parts).items():
            hits.setdefault(name, round(float(d), 1))
    return {'handle_deg': angle_deg, 'from_mm': reach, 'pass': not hits,
            'blocked_at_distance_mm': hits}


def stops(scene, centre, bottom, angle_deg, parts, limit=60., step=1.):
    """Turn the engaged spanner both ways from `angle_deg` until it first touches a part."""
    result = {}
    for sense, key in ((1., 'ccw_from_above'), (-1., 'cw_from_above')):
        row = {'free_deg': limit, 'stop_part': None}
        for k in np.arange(step, limit + step/2, step):
            hit = scene.blocked(spanner(centre, bottom, np.radians(angle_deg + sense*k)), parts)
            if hit:
                row = {'free_deg': round(float(k - step), 1), 'stop_part': sorted(hit)}
                break
        result[key] = row
    return result


def check(cad, steps_path):
    data = json.loads(steps_path.read_text(encoding='utf-8'))
    scene = Scene(cad)
    steps = {s['id']: s for s in data['steps']}
    feet = steps['yaw-bracket-feet']
    installed = feet['fixed'] + [i for m in feet['moves'] for i in m['ids']]
    report = {'socket': {'outer_diameter_mm': SOCKET_OUTER_MM, 'length_mm': SOCKET_LENGTH_MM},
              'yaw_bracket_feet': {},
              'bottom_hatch': 'the hex recesses on the bars hold the hatch nuts; no tool is needed on the nut side'}
    for i in range(4):
        nut = scene.mesh(f'YawBracketFootNut{i}')
        centre, top = nut.bounds.mean(axis=0), nut.bounds[1][2]
        parts = [p for p in installed if p not in (f'YawBracketFootNut{i}', f'YawBracketFoot{i}')]
        def socket_hits(outer):
            socket = trimesh.creation.cylinder(radius=outer/2, height=SOCKET_LENGTH_MM, sections=48)
            socket.apply_translation((centre[0], centre[1], top - 2. + SOCKET_LENGTH_MM/2))
            return scene.blocked(socket, parts)
        blocked = socket_hits(SOCKET_OUTER_MM)
        widest, stop = SOCKET_OUTER_MM, None
        for outer in np.arange(SOCKET_OUTER_MM + .1, 12.01, .1):
            hit = socket_hits(round(float(outer), 1))
            if hit:
                stop = sorted(hit)
                break
            widest = round(float(outer), 1)
        report['yaw_bracket_feet'][f'YawBracketFootNut{i}'] = {
            'tool': '5.5 mm socket from above', 'pass': not blocked, 'blocking_parts': sorted(blocked),
            'widest_socket_outer_mm': widest if not blocked else None, 'wider_blocked_by': stop}
    return report


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('steps', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = check(args.cad, args.steps)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    for group in ('yaw_bracket_feet',):
        for nut, row in result[group].items():
            print(group, nut, 'PASS' if row['pass'] else 'FAIL', row.get('widest_socket_outer_mm', ''), row['blocking_parts'][:6])
