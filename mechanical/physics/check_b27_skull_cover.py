"""Check the B27 skull covers against fixed acceptance conditions.

The conditions live in mechanical/revisions/b27/cover-spec.json and are not edited by the
implementer. The implementer declares the cover parts in a small JSON file (see
mechanical/revisions/b27/WORK.md, "Cover declaration"). Both assemblies are read from
export_cad.py --world exports, so every check sees the same meshes and motion groups that the
other repository checkers use.

Checks
  exposure   Mechanism visible from 9 orthographic views per side, counted only where the hit
             point lies in the lateral zone (temple, cheek, jaw hinge). Skull, declared covers,
             eyes, lids, the neck mast and the base are not mechanism. Cover screws may be seen.
  anatomy    Every visible point of a declared cover, and every visible point of skull 28/29 or
             jaw 30 that moved more than 0.3 mm from the baseline, must lie on the registered
             BoneHub reference: 95% within 1.5 mm, nowhere more than 2.5 mm outside it. For the
             cranium the reference is either the bone or the bone with the temple filled flush
             (temple-fill meshes: the lateral height field closed with a 15 mm disc).
  clearance  Every part that is new or whose world mesh changed, against every other part of
             the head, neck and jaw, through the neck, eye, blink and jaw ranges (check_head.pose).
             Moving pairs keep 0.30 mm or no less than the same pair had in the baseline. Rigid
             pairs may not overlap more than they did in the baseline, except a declared cover
             screw with its own cover and its declared host.
  print      New printed parts: one closed body, under 2 mm² thinner than 0.8 mm, under 3% of the
             surface thinner than 2.0 mm. Changed printed parts: no worse than the baseline.
  removal    Each cover slides out 40 mm along its declared direction with its screws removed. It may
             slide along a face it touches, but no vertex of it or of another part may go more
             than 0.05 mm into the other at any 0.5 mm step.

    python mechanical/physics/check_b27_skull_cover.py build/b27/cad build/b26/cad \
        mechanical/revisions/b27/cover-parts.json build/b27/cover-check.json --images build/b27/cover-check
"""

from argparse import ArgumentParser
from itertools import product
import json
from pathlib import Path
import sys

import fcl
import numpy as np
import trimesh as tr
from trimesh.collision import mesh_to_BVH

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
from check_head import AXES_BY_MOTION, pose, sweep_angles  # noqa: E402

SPEC = ROOT/'mechanical/revisions/b27/cover-spec.json'
import os
DEBUG = bool(os.environ.get('R5_DEBUG'))
N_AXES = 5          # neck, eye pitch, eye yaw, blink, jaw (check_head.ANGLES order)


class Export:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.layout = json.loads((self.dir/'cad_parts.json').read_text(encoding='utf-8'))
        self.motion = self.layout['world_motion']
        self.sha = self.layout.get('world_sha256', {})
        self.rows = {row['name']: row for row in self.layout['parts']}
        self._mesh = {}
        self._bvh = {}

    def bvh(self, name):
        if name not in self._bvh:
            self._bvh[name] = mesh_to_BVH(self.mesh(name))
        return self._bvh[name]

    def mesh(self, name):
        if name not in self._mesh:
            self._mesh[name] = tr.load_mesh(self.dir/'world'/f'{name}.stl', process=True)
        return self._mesh[name]

    def label(self, name):
        return self.rows.get(name, {}).get('label', name)

    def printed(self, name):
        return bool(self.rows.get(name, {}).get('printed', False))


def rotation(angle, axis):
    return tr.transformations.rotation_matrix(np.radians(angle), axis)


# ---------------------------------------------------------------- exposure
def view_rays(spec, side, yaw, tilt):
    v = spec['views']
    look = np.array([-side, 0., 0.])
    look = rotation(yaw, (0, 0, 1))[:3, :3] @ look
    right = np.cross(look, (0, 0, 1.))
    right /= np.linalg.norm(right)
    look = rotation(tilt, right)[:3, :3] @ look
    up = np.cross(right, look)
    s = np.arange(-v['half_size_mm'], v['half_size_mm'], v['step_mm'])
    a, b = np.meshgrid(s, -s)
    origins = np.asarray(v['centre_mm'])+a.ravel()[:, None]*right+b.ravel()[:, None]*up-look*400.
    return origins, np.tile(look, (len(origins), 1)), a.shape


def in_zone(points, spec, side):
    z = spec['lateral_zone']
    x, y, h = points[:, 0]*side, points[:, 1], points[:, 2]
    base = z['skull_base_excluded']
    return ((x >= z['abs_x_min_mm']) & (y >= z['y_min_mm']) & (h >= z['z_min_mm']) & (h <= z['z_max_mm'])
            & ~((h < base['z_below_mm']) & (y > base['y_above_mm'])))


def exposure(cad, spec, decl, images):
    names = [n for n in cad.motion if (cad.dir/'world'/f'{n}.stl').exists()]
    meshes, owner = [], []
    for n in names:
        m = cad.mesh(n)
        if len(m.faces):
            meshes.append(m)
            owner += [n]*len(m.faces)
    scene = tr.util.concatenate(meshes)
    owner = np.array(owner)
    ray = tr.ray.ray_pyembree.RayMeshIntersector(scene)
    covers = {c['part'] for c in decl['covers']}
    skin = set(spec['skin_parts']) | covers
    fasteners = {f['part']: c['side'] for c in decl['covers'] for f in c['fasteners']}
    allowed = set(spec['always_visible_parts']) | {n for n in names if cad.motion[n] in spec['always_visible_motion_groups']}
    step2 = spec['views']['step_mm']**2
    report = {'views': [], 'sides': {}}
    hits_on_skin = []
    for side, side_name in ((1, 'right'), (-1, 'left')):
        total = 0.
        parts_total = {}
        for yaw, tilt in product(spec['views']['yaw_deg'], spec['views']['tilt_deg']):
            o, d, shape = view_rays(spec, side, yaw, tilt)
            loc, ri, ti = ray.intersects_location(o, d, multiple_hits=False)
            hit_owner = owner[ti]
            zone = in_zone(loc, spec, side)
            mech = zone & ~np.isin(hit_owner, list(skin | allowed | set(fasteners)))
            seen_fasteners = sorted(set(hit_owner[zone & np.isin(hit_owner, list(fasteners))]))
            area = float(mech.sum()*step2)
            total += area
            per = {}
            for n, c in zip(*np.unique(hit_owner[mech], return_counts=True)):
                per[n] = round(float(c*step2), 1)
                parts_total[n] = parts_total.get(n, 0.)+float(c*step2)
            report['views'].append({'side': side_name, 'yaw_deg': yaw, 'tilt_deg': tilt,
                                    'mechanism_mm2': round(area, 1), 'by_part': per,
                                    'visible_cover_fasteners': seen_fasteners,
                                    'pass': area <= spec['exposure_limit_mm2']['per_view']})
            skin_hit = zone & np.isin(hit_owner, list(skin))
            hits_on_skin.append((loc[skin_hit], hit_owner[skin_hit]))
            if images is not None:
                save_view(images/f'exposure-{side_name}-yaw{yaw:+d}-tilt{tilt:+d}.png', shape, ri, ti, owner,
                          scene, d[0], mech, zone, skin, allowed, set(fasteners))
        side_fasteners = [f for f, s in fasteners.items() if s == side_name]
        report['sides'][side_name] = {
            'mechanism_mm2_all_views': round(total, 1),
            'by_part_all_views': {cad.label(k): round(v, 1) for k, v in sorted(parts_total.items(), key=lambda kv: -kv[1])},
            'declared_cover_fasteners': len(side_fasteners),
            'pass': (total <= spec['exposure_limit_mm2']['per_side_all_views']
                     and len(side_fasteners) <= spec['visible_cover_fasteners_per_side_max'])}
    report['pass'] = all(v['pass'] for v in report['views']) and all(s['pass'] for s in report['sides'].values())
    del ray, scene
    __import__('gc').collect()
    points = np.vstack([h[0] for h in hits_on_skin]) if hits_on_skin else np.zeros((0, 3))
    owners = np.concatenate([h[1] for h in hits_on_skin]) if hits_on_skin else np.zeros(0, str)
    return report, points, owners


def save_view(path, shape, ri, ti, owner, scene, look, mech, zone, skin, allowed, fasteners):
    from PIL import Image
    img = np.full((shape[0]*shape[1], 3), (24, 32, 44), float)
    shade = np.clip(np.abs(scene.face_normals[ti] @ look), 0, 1)*.7+.3
    hit_owner = owner[ti]
    col = np.tile([150., 150., 150.], (len(ti), 1))
    col[np.isin(hit_owner, list(skin))] = (236, 228, 210)
    col[np.isin(hit_owner, list(fasteners))] = (90, 170, 240)
    col[mech] = (225, 60, 60)
    col[~zone & ~np.isin(hit_owner, list(skin))] *= .55
    img[ri] = col*shade[:, None]
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img.reshape(shape+(3,)).astype(np.uint8)).save(path)


# ---------------------------------------------------------------- anatomy
def anatomy(cad, base, spec, decl, points, owners):
    a = spec['anatomy']
    refs = {'right': tr.load_mesh(ROOT/a['cranium']['right']), 'left': tr.load_mesh(ROOT/a['cranium']['left']),
            'mandible': tr.load_mesh(ROOT/a['mandible'])}
    fills = {k: tr.proximity.ProximityQuery(tr.load_mesh(ROOT/v)) for k, v in a['temple_fill'].items()}
    queries = {k: tr.proximity.ProximityQuery(m) for k, m in refs.items()}

    def deviation(key, pts):
        """Distance to the reference: the bone itself, or the bone with the temple filled flush."""
        bone = queries[key].signed_distance(pts)                      # > 0 inside
        if key == 'mandible':
            return np.abs(bone), np.maximum(0., -bone)
        filled = np.maximum(bone, fills[key].signed_distance(pts))
        return np.minimum(np.abs(bone), np.abs(filled)), np.maximum(0., -filled)

    covers = {c['part']: c for c in decl['covers']}
    rows = {}
    for name in sorted(set(owners)):
        pts = points[owners == name]
        if name not in covers:
            if name not in base.motion or base.sha.get(name) == cad.sha.get(name):
                continue
            moved = np.abs(tr.proximity.ProximityQuery(base.mesh(name)).signed_distance(pts)) > a['changed_skin_threshold_mm']
            pts = pts[moved]
        if len(pts) == 0:
            continue
        pts = pts[np.random.default_rng(7).permutation(len(pts))[:20000]]
        follows = covers[name]['follows'] if name in covers else ('mandible' if cad.motion.get(name) == 'jaw' else 'cranium')
        dev, out = [], []
        for side, sel in (('right', pts[:, 0] >= 0), ('left', pts[:, 0] < 0)):
            if not sel.any():
                continue
            d, b = deviation('mandible' if follows == 'mandible' else side, pts[sel])
            dev.append(d)
            out.append(b)
        dev, out = np.concatenate(dev), np.concatenate(out)
        p95 = float(np.quantile(dev, .95))
        bulge = float(out.max())
        rows[cad.label(name)] = {'part': name, 'reference': follows, 'visible_points': int(len(dev)),
                                 'abs_deviation_p95_mm': round(p95, 2), 'outward_bulge_max_mm': round(bulge, 2),
                                 'pass': p95 <= a['abs_deviation_p95_max_mm'] and bulge <= a['outward_bulge_max_mm']}
    return {'surfaces': rows, 'pass': all(r['pass'] for r in rows.values())}


# ---------------------------------------------------------------- clearance
def angle_grid(cad, spec):
    c = spec['clearance']
    neck, _, _, _, jaw = sweep_angles(cad.layout)
    neck = sorted(set(np.round(np.linspace(min(neck), max(neck), c['neck_samples']), 4)) | {0.})
    jaw = sorted(set(np.round(np.linspace(0., max(jaw), c['jaw_samples']), 4)))
    return [neck, sorted(set(c['eye_pitch_deg']) | {0.}), sorted(set(c['eye_yaw_deg']) | {0.}),
            sorted(set(c['blink_deg']) | {0.}), jaw]


def poses_for(kind, grid, layout):
    axes = AXES_BY_MOTION.get(kind, ())
    out = []
    for values in product(*(grid[i] for i in axes)):
        angles = np.zeros(N_AXES)
        angles[list(axes)] = values
        out.append(pose(kind, angles, layout))
    return out


def swept_box(mesh, transforms):
    corners = tr.bounds.corners(mesh.bounds)
    pts = np.vstack([tr.transform_points(corners, t) for t in transforms])
    return pts.min(axis=0), pts.max(axis=0)


def overlap_volume(a, b, tx=None):
    b = b.copy() if tx is None else b.copy().apply_transform(tx)
    if not (a.is_volume and b.is_volume):
        return None
    cut = tr.boolean.intersection([a, b], engine='manifold', check_volume=False)
    return float(max(0., cut.volume))


def pair_min(export, a, b, grid, request_limit):
    """Smallest distance of a pair over the relative poses (fcl), and the worst overlap if any."""
    ka, kb = export.motion[a], export.motion[b]
    if ka == kb:
        axes = []
    else:
        axes = sorted(set(AXES_BY_MOTION.get(ka, ())) | set(AXES_BY_MOTION.get(kb, ())))
    x = fcl.CollisionObject(export.bvh(a))
    y = fcl.CollisionObject(export.bvh(b))
    best, worst = np.inf, None
    for values in product(*(grid[i] for i in axes)) if axes else [()]:
        angles = np.zeros(N_AXES)
        angles[axes] = values
        tx = np.linalg.solve(pose(ka, angles, export.layout), pose(kb, angles, export.layout))
        y.setTransform(fcl.Transform(tx[:3, :3].copy(), tx[:3, 3].copy()))
        if fcl.collide(x, y, fcl.CollisionRequest(), fcl.CollisionResult()):
            # The first colliding pose decides the pair: report its overlap and stop.
            vol = overlap_volume(export.mesh(a), export.mesh(b), tx)
            if axes and vol is not None and vol <= 0.01:
                best = 0.
                continue
            worst = {'angles_deg': [float(v) for v in angles], 'overlap_mm3': vol}
            best = 0.
            break
        d = fcl.distance(x, y, fcl.DistanceRequest(), fcl.DistanceResult())
        best = min(best, d)
    return best, worst, bool(axes)


def clearance(cad, base, spec, decl):
    c = spec['clearance']
    grid = angle_grid(cad, spec)
    upper = [n for n in cad.motion if cad.motion[n] not in ('fixed', 'hatch') and (cad.dir/'world'/f'{n}.stl').exists()]
    targets = [n for n in upper if base.sha.get(n) != cad.sha.get(n)]
    allowed = set()
    for cover in decl['covers']:
        for f in cover['fasteners']:
            allowed.add(tuple(sorted((f['part'], cover['part']))))
            allowed.add(tuple(sorted((f['part'], f['host']))))
    boxes = {n: swept_box(cad.mesh(n), poses_for(cad.motion[n], grid, cad.layout)) for n in upper if len(cad.mesh(n).faces)}
    rows, failures, checked = [], [], set()
    for a in targets:
        if a not in boxes:
            continue
        cad._bvh.clear()
        base._bvh.clear()
        for b in upper:
            pair = tuple(sorted((a, b)))
            if a == b or pair in checked or b not in boxes:
                continue
            checked.add(pair)
            gap = np.maximum(boxes[a][0]-boxes[b][1], boxes[b][0]-boxes[a][1]).max()
            if gap > 1.0:
                continue
            if DEBUG:
                import resource
                print('pair', pair, round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024), 'MB', flush=True)
            best, worst, moving = pair_min(cad, pair[0], pair[1], grid, None)
            row = {'pair': [cad.label(pair[0]), cad.label(pair[1])], 'parts': list(pair), 'moving': moving,
                   'min_clearance_mm': None if not np.isfinite(best) else round(float(best), 3), 'overlap': worst}
            if pair in allowed:
                row['declared_screw_contact'] = True
                row['pass'] = True
            elif moving:
                ok = best >= c['moving_pair_min_mm'] and worst is None
                if not ok and all(p in base.motion for p in pair):
                    b_best, b_worst, _ = pair_min(base, pair[0], pair[1], grid, None)
                    row['baseline_min_clearance_mm'] = round(float(b_best), 3)
                    ok = worst is None and best >= min(c['moving_pair_min_mm'], b_best)-c['baseline_tolerance_mm']
                row['pass'] = bool(ok)
            else:
                vol = 0. if worst is None else (worst['overlap_mm3'] if worst['overlap_mm3'] is not None else np.inf)
                ok = vol <= c['static_overlap_growth_max_mm3']
                if not ok and all(p in base.motion for p in pair):
                    b_vol = overlap_volume(base.mesh(pair[0]), base.mesh(pair[1])) or 0.
                    row['baseline_overlap_mm3'] = round(b_vol, 3)
                    ok = vol <= b_vol+c['static_overlap_growth_max_mm3']
                row['pass'] = bool(ok)
            rows.append(row)
            if not row['pass']:
                failures.append(row)
    return {'changed_or_new_parts': [cad.label(n) for n in targets], 'pairs_checked': len(rows),
            'grid_deg': {'neck': grid[0], 'eye_pitch': grid[1], 'eye_yaw': grid[2], 'blink': grid[3], 'jaw': grid[4]},
            'failures': failures, 'closest': sorted([r for r in rows if r['min_clearance_mm'] is not None and r['moving']],
                                                    key=lambda r: r['min_clearance_mm'])[:12],
            'pass': not failures}


# ---------------------------------------------------------------- print
def thin_areas(mesh, per_mm2):
    n = int(min(400000, max(20000, mesh.area*per_mm2)))
    pts, face = tr.sample.sample_surface_even(mesh, n, seed=3)
    normal = mesh.face_normals[face]
    start = pts-normal*1e-3
    loc, ri, _ = tr.ray.ray_pyembree.RayMeshIntersector(mesh).intersects_location(start, -normal, multiple_hits=False)
    t = np.full(len(pts), np.inf)
    t[ri] = np.linalg.norm(loc-start[ri], axis=1)
    a = mesh.area/len(pts)
    return float((t < .8).sum()*a), float((t < 2.).sum()*a), float(mesh.area)


def printing(cad, base, spec, decl):
    p = spec['print']
    covers = {c['part'] for c in decl['covers']}
    rows = {}
    for n in cad.motion:
        if not (cad.dir/'world'/f'{n}.stl').exists():
            continue
        new = n not in base.motion
        changed = not new and base.sha.get(n) != cad.sha.get(n)
        if not (new or changed) or not (cad.printed(n) or n in covers):
            continue
        m = cad.mesh(n)
        below08, below20, area = thin_areas(m, p['samples_per_mm2'])
        row = {'part': n, 'new': new, 'closed': bool(m.is_watertight), 'bodies': len(m.split(only_watertight=False)),
               'area_below_0p8_mm2': round(below08, 1), 'area_below_2p0_fraction': round(below20/area, 4)}
        ok = row['closed'] and row['bodies'] == 1
        if new:
            ok &= below08 <= p['new_part_area_below_0p8_mm2_max'] and below20/area <= p['new_part_area_below_2p0_fraction_max']
        else:
            b08, b20, barea = thin_areas(base.mesh(n), p['samples_per_mm2'])
            row['baseline_area_below_0p8_mm2'] = round(b08, 1)
            row['baseline_area_below_2p0_fraction'] = round(b20/barea, 4)
            ok &= (below08 <= b08+p['changed_part_area_below_0p8_growth_mm2_max']
                   and below20/area <= b20/barea+p['changed_part_area_below_2p0_growth_fraction_max'])
        row['pass'] = bool(ok)
        rows[cad.label(n)] = row
    return {'parts': rows, 'pass': all(r['pass'] for r in rows.values())}


# ---------------------------------------------------------------- removal
def penetration(a, b):
    """Deepest vertex of either mesh inside the other, inside their common bounding box (mm)."""
    lo = np.maximum(a.bounds[0], b.bounds[0])-.1
    hi = np.minimum(a.bounds[1], b.bounds[1])+.1
    depth = 0.
    for p, q in ((a, b), (b, a)):
        pts = p.vertices[np.all((p.vertices >= lo) & (p.vertices <= hi), axis=1)]
        if len(pts) and q.is_volume:
            depth = max(depth, float(tr.proximity.ProximityQuery(q).signed_distance(pts).max()))
    return depth


def removal(cad, spec, decl):
    r = spec['removal']
    rows = {}
    others = [n for n in cad.motion if cad.motion[n] not in ('fixed', 'hatch') and (cad.dir/'world'/f'{n}.stl').exists()]
    for cover in decl['covers']:
        name = cover['part']
        skip = {name} | {f['part'] for f in cover['fasteners']}
        direction = np.asarray(cover['removal_direction'], float)
        direction /= np.linalg.norm(direction)
        mesh = cad.mesh(name)
        lo, hi = mesh.bounds
        reach = np.vstack([lo, hi, lo+direction*r['distance_mm'], hi+direction*r['distance_mm']])
        box_lo, box_hi = reach.min(axis=0)-1, reach.max(axis=0)+1
        near = [n for n in others if n not in skip and len(cad.mesh(n).faces)
                and np.all(cad.mesh(n).bounds[0] <= box_hi) and np.all(cad.mesh(n).bounds[1] >= box_lo)]
        x = fcl.CollisionObject(cad.bvh(name))
        objs = {n: fcl.CollisionObject(cad.bvh(n)) for n in near}
        blocked, closest = None, (np.inf, None, None)
        for s in np.arange(r['step_mm'], r['distance_mm']+1e-9, r['step_mm']):
            x.setTransform(fcl.Transform(np.eye(3), direction*s))
            for n, y in objs.items():
                if fcl.collide(x, y, fcl.CollisionRequest(), fcl.CollisionResult()):
                    depth = penetration(mesh.copy().apply_translation(direction*s), cad.mesh(n))
                    if depth > r['penetration_max_mm']:
                        blocked = {'part': cad.label(n), 'at_mm': round(float(s), 2), 'depth_mm': round(depth, 3)}
                        break
                    continue
                if s >= r['measure_from_mm']:
                    d = fcl.distance(x, y, fcl.DistanceRequest(), fcl.DistanceResult())
                    if d < closest[0]:
                        closest = (d, n, s)
            if blocked:
                break
        rows[name] = {'direction': direction.round(3).tolist(), 'blocked': blocked,
                      'min_clearance_after_mm': round(float(closest[0]), 3) if np.isfinite(closest[0]) else None,
                      'closest_part': cad.label(closest[1]) if closest[1] else None,
                      'pass': blocked is None}
    return {'covers': rows, 'pass': all(v['pass'] for v in rows.values())}


# ---------------------------------------------------------------- declaration
def check_declaration(cad, base, decl):
    problems = []
    for cover in decl['covers']:
        if cover['part'] in base.motion:
            problems.append(f"cover {cover['part']} already exists in the baseline; covers must be new parts")
        if cover['part'] not in cad.motion:
            problems.append(f"cover {cover['part']} is not in the export")
        elif cad.motion[cover['part']] not in ('head', 'jaw'):
            problems.append(f"cover {cover['part']} must move with the head or the jaw, not {cad.motion[cover['part']]}")
        if cover['follows'] not in ('cranium', 'mandible'):
            problems.append(f"cover {cover['part']}: follows must be cranium or mandible")
        if cover['follows'] == 'mandible' and cad.motion.get(cover['part']) != 'jaw':
            problems.append(f"cover {cover['part']} follows the mandible but does not move with the jaw")
        if len(cover['fasteners']) < 2:
            problems.append(f"cover {cover['part']} needs at least two screws")
        for f in cover['fasteners']:
            for key in ('part', 'host'):
                if f[key] not in cad.motion:
                    problems.append(f"cover {cover['part']}: {key} {f[key]} is not in the export")
    return problems


def main():
    parser = ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('cad', type=Path, help='export_cad.py --world output of the candidate')
    parser.add_argument('baseline', type=Path, help='export_cad.py --world output of the baseline (B26)')
    parser.add_argument('declaration', type=Path, help='cover declaration JSON')
    parser.add_argument('report', type=Path)
    parser.add_argument('--images', type=Path)
    parser.add_argument('--only', nargs='*', choices=('exposure', 'anatomy', 'clearance', 'print', 'removal'))
    args = parser.parse_args()
    spec = json.loads(SPEC.read_text(encoding='utf-8'))
    decl = json.loads(args.declaration.read_text(encoding='utf-8'))
    cad, base = Export(args.cad), Export(args.baseline)
    run = set(args.only or ('exposure', 'anatomy', 'clearance', 'print', 'removal'))
    report = {'spec_sha256': __import__('hashlib').sha256(SPEC.read_bytes()).hexdigest(),
              'cad_sha256': cad.layout.get('source_sha256'), 'baseline_sha256': base.layout.get('source_sha256'),
              'declaration': decl}
    problems = check_declaration(cad, base, decl)
    report['declaration_problems'] = problems
    if 'exposure' in run or 'anatomy' in run:
        report['exposure'], pts, owners = exposure(cad, spec, decl, args.images)
        print('exposure', {k: v['mechanism_mm2_all_views'] for k, v in report['exposure']['sides'].items()},
              'pass' if report['exposure']['pass'] else 'FAIL', flush=True)
        if 'anatomy' in run:
            report['anatomy'] = anatomy(cad, base, spec, decl, pts, owners)
            print('anatomy', 'pass' if report['anatomy']['pass'] else 'FAIL', flush=True)
    if 'clearance' in run:
        report['clearance'] = clearance(cad, base, spec, decl)
        print('clearance', len(report['clearance']['failures']), 'failures', flush=True)
    if 'print' in run:
        report['print'] = printing(cad, base, spec, decl)
        print('print', 'pass' if report['print']['pass'] else 'FAIL', flush=True)
    if 'removal' in run and decl['covers']:
        report['removal'] = removal(cad, spec, decl)
        print('removal', 'pass' if report['removal']['pass'] else 'FAIL', flush=True)
    sections = [k for k in ('exposure', 'anatomy', 'clearance', 'print', 'removal') if k in report]
    report['pass'] = not problems and all(report[k]['pass'] for k in sections) and run == {
        'exposure', 'anatomy', 'clearance', 'print', 'removal'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=float)+'\n', encoding='utf-8')
    print('B27 cover check', 'PASS' if report['pass'] else 'FAIL', flush=True)
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
