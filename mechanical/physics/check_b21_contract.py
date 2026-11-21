"""Release gate for modelled B21 assembly, purchased hardware and light-load evidence."""

from argparse import ArgumentParser
from collections import Counter
import csv
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

import numpy as np

from check_b19_assembly import B22_CAMERA_PATH_CHECKS, World, assembly_plan, plan_hash


XL330 = 'https://emanual.robotis.com/docs/en/dxl/x/xl330-m077/'
XL330_BLINK = 'https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/'
XL430 = 'https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/'
OPENRB = 'https://emanual.robotis.com/docs/en/parts/controller/openrb-150/'
CAMERA = 'https://github.com/INNO-MAKER/U20CAM-1080P-S1'


@dataclass(frozen=True)
class VendorInterface:
    host: str
    diameter_mm: float
    source: str
    mount: str
    bolt: str | None = None


def vendor_interfaces():
    mounts = {}
    for host, prefix, count, mount in (
        ('Part041', 'eyePitchHead', 4, 'case'), ('Part038', 'eyeYawHead', 4, 'case'),
        ('Part045', 'blinkMotorHead', 4, 'case'), ('Jaw_XL330_M288_Jaw', 'jawMotorHead', 4, 'case'),
        ('Part041', 'EyePitchHornScrew', 2, 'horn'), ('Part038', 'EyeYawHornScrew', 3, 'horn'),
        ('Part045', 'BlinkHornScrew', 2, 'horn'), ('Jaw_XL330_M288_Jaw', 'JawHornScrew', 2, 'horn'),
    ):
        source = XL330_BLINK if host in ('Part045', 'Jaw_XL330_M288_Jaw') else XL330
        mounts.update({f'{prefix}{i}': VendorInterface(host, 2., source, mount) for i in range(count)})
    for host, prefix, count, size, mount in (
        ('Part017', 'XL430YawSideL', 2, 2.5, 'case'), ('Part017', 'XL430YawSideR', 2, 2.5, 'case'),
        ('Part018', 'XL430PitchSide', 2, 2.5, 'case'), ('Part018', 'XL430PitchKeeper', 2, 2.5, 'case'),
        ('Part017', 'hornBolt', 4, 2., 'horn'), ('Part018', 'pitchHornBolt', 4, 2., 'horn'),
    ):
        mounts.update({f'{prefix}{i}': VendorInterface(host, size, XL430, mount) for i in range(count)})
    for i in range(4):
        bolt = f'openrbBolt{i}'
        mounts[bolt] = VendorInterface('Part069', 2., OPENRB, 'supplied PCB through hole')
        mounts[f'openrbNut{i}'] = VendorInterface('Part069', 2., OPENRB, 'supplied PCB through hole', bolt)
    for side in ('Left', 'Right'):
        bolt = f'CameraPCBScrew{side}'
        description = 'supplied PCB Ø2.2 mm hole, nominal centre inferred from vendor photos'
        mounts[bolt] = VendorInterface('Part067', 2., CAMERA, description)
        mounts[f'CameraPCBNut{side}'] = VendorInterface('Part067', 2., CAMERA, description, bolt)
    return mounts


VENDOR = vendor_interfaces()
THREAD = re.compile(r'\bM([1-9]\d*(?:\.\d+)?)\b', re.IGNORECASE)
CHECKED_LIGHT_CASES = {(0., 0.), (0., .25), (0., .50), (0., 1.), (.25, .25),
                       (.25, 0.), (.50, 0.), (1., 0.)}
SMOOTH_LINK_PINS = {'BlinkPivotServo', 'BlinkPivotDrive', 'BlinkPivotUpperL', 'BlinkPivotUpperR',
                    'BlinkPivotLowerL', 'BlinkPivotLowerR', 'EyeYawDrivePivot'}


def read(path):
    return json.loads(path.read_bytes())


def outcome(name, *, failures=(), unknown=(), **details):
    failures, unknown = list(failures), list(unknown)
    status = 'fail' if failures else 'unknown' if unknown else 'pass'
    return {'check': name, 'status': status, 'failures': failures, 'unknown': unknown, **details}


def bom_stock(bom):
    kinds = {'나사': 'bolt', '너트': 'nut', '와셔': 'washer'}
    stock = Counter()
    with bom.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            if row['구분'] in kinds:
                kind = kinds[row['구분']]
                item = row['품목']
                diameter = float(THREAD.search(item)[1])
                length = int(re.search(r'×\s*(\d+)\b', item)[1]) if kind == 'bolt' else None
                stock[kind, diameter, length] += int(row['필요 수량'])
    if not stock:
        raise ValueError('No standard fasteners declared in BOM')
    return stock


def stock_label(key):
    kind, size, length = key
    return f'{kind} M{size:g}' + (f' × {length:d}' if length is not None else '')


def transverse_vectors(axis):
    u = np.cross(axis, [1., 0., 0.] if abs(axis[0]) < .8 else [0., 1., 0.])
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    theta = np.arange(8)*np.pi/4
    return np.cos(theta)[:, None]*u + np.sin(theta)[:, None]*v


def ray_distances(mesh, sources, rays):
    locations, ray, _ = mesh.ray.intersects_location(sources, rays, multiple_hits=True)
    ranges = np.full(len(sources), np.inf)
    np.minimum.at(ranges, ray, np.linalg.norm(locations-sources[ray], axis=1))
    return ranges


def bore_radii(mesh, start, axis, length):
    """Measure radial face distances in the exported mesh every 0.2 mm along the axis."""
    center, axis = np.asarray(start), np.asarray(axis, float)
    if not np.isclose(np.linalg.norm(axis), 1.):
        raise ValueError('Non-unit fastener axis')
    directions = transverse_vectors(axis)
    probes = center + np.arange(.10, length-.05, .20)[:, None]*axis
    sources = np.repeat(probes, len(directions), axis=0)
    rays = np.tile(directions, (len(probes), 1))
    return ray_distances(mesh, sources, rays).reshape(-1, len(directions))


def bore_span(radii, min_radius, max_radius):
    bounded = np.all((radii >= min_radius) & (radii <= max_radius), axis=1)
    if len(bounded) < 3 or not (bounded[:-2] & bounded[1:-1] & bounded[2:]).any():
        return None
    return {'sections_at_0p20_mm': int(bounded.sum()),
            'diameter_mm_bounds': [round(float(radii[bounded].min()*2), 3),
                                   round(float(radii[bounded].max()*2), 3)]}


def port_sections(world, name, host, size):
    """Locate a coaxial vendor bore using radial rays through the purchased mesh."""
    _, length, seat, axis = world.screw(name)
    return bore_span(bore_radii(world.mesh(host), seat, axis, length), .34*size, .69*size)


def installed_fasteners(plan, world, layout, spec, bom):
    occupied = {}
    all_parts = set()
    stock = Counter()
    seen, verified = {}, {}
    failures, unknown = [], []
    for row in plan:
        fixed = occupied.setdefault(row['ctx'], set())
        for role in ('merge', 'merge2'):
            if role in row:
                fixed.update(occupied.pop(row[role][0]))
        for role in ('place', 'place2', 'pins', 'pins2', 'path', 'nuts', 'nuts2'):
            if role in row:
                fixed.update(row[role][0])
                all_parts.update(row[role][0])
        staged = list(row.get('bolts', ()))
        grouped = [names[0] for key, names in row.items() if key in ('nuts', 'nuts2')]
        all_parts.update(staged)
        for role, ids in [('bolt', staged), *(('tail', names) for names in grouped)]:
            for name in ids:
                if name in seen:
                    failures.append(f'{name}: appears in two installing operations')
                    continue
                seen[name] = row['id']
                try:
                    if role == 'bolt':
                        size, length, _, _ = world.screw(name)
                        key = ('bolt', size, round(length))
                    else:
                        item = world.rows[name]
                        key = (item['type'], item['size'], None)
                        if key[0] not in ('nut', 'washer'):
                            raise ValueError('Wrong part class')
                except (KeyError, ValueError, TypeError):
                    unknown.append(f'{name}: no typed installed fastener geometry')
                    continue
                stock[key] += 1
                if key[0] == 'washer' or key[1] == 3:
                    continue
                allowance = VENDOR.get(name)
                if allowance is None or allowance.diameter_mm != key[1]:
                    failures.append(f'{name}: {stock_label(key)} is not at a declared vendor interface')
                    continue
                if allowance.host not in fixed:
                    failures.append(f'{name}: vendor host {allowance.host} is missing at {row["id"]}')
                    continue
                try:
                    proof = port_sections(world, allowance.bolt or name, allowance.host, key[1])
                except (OSError, ValueError, KeyError, TypeError):
                    proof = None
                if proof is None:
                    unknown.append(f'{name}: no radial bore evidence in {allowance.host}')
                    continue
                verified[name] = {'host': allowance.host, 'mount': allowance.mount, 'source': allowance.source, **proof}
        fixed.update(staged)
    unused = {row['name'] for row in spec} - all_parts
    missing_model = {row['name'] for row in spec} - set(layout['world_motion'])
    if unused:
        failures.append(f'Modelled hardware missing from assembly: {", ".join(sorted(unused))}')
    if missing_model:
        unknown.append(f'Hardware missing from CAD export: {", ".join(sorted(missing_model))}')
    for name in sorted(all_parts-seen.keys()):
        if name in world.screws or world.rows.get(name, {}).get('type') in ('bolt', 'head', 'nut'):
            failures.append(f'{name}: threaded hardware omitted from installing operations')
    declared = bom_stock(bom)
    for key in sorted(stock.keys() | declared.keys()):
        if stock[key] != declared[key]:
            failures.append(f'{stock_label(key)}: assembly {stock[key]} vs BOM {declared[key]}')
    return outcome('fastener_stock', failures=failures, unknown=unknown, vendor_interfaces=verified,
                   stock={stock_label(key): count for key, count in sorted(stock.items())})


def pivot_check(plan, world, specs, report, digest):
    failures, unknown = [], []
    bearings = {}
    axial_floats = {}
    types = {row['name']: row for row in specs}
    installed = {item for row in plan for role in ('pins', 'pins2') for item in row.get(role, ([], None))[0]}
    for name in sorted(SMOOTH_LINK_PINS):
        entry = types.get(name, {})
        if name not in installed or entry.get('kind') != 'pin' or len(entry.get('shapes', [])) != 1:
            unknown.append(f'{name}: no declared smooth pin installed in the assembly')
            continue
        section, radius, length, start, axis = entry['shapes'][0]
        if section != 'cyl' or abs(radius-1.) > .005 or length <= 0:
            failures.append(f'{name}: not a plain Ø2 mm bearing pin')
            continue
        try:
            mesh = world.mesh(name)
        except (OSError, ValueError):
            unknown.append(f'{name}: no usable CAD pin mesh')
            continue
        samples = mesh.vertices-np.asarray(start)
        axis = np.asarray(axis, float)
        if not np.isclose(np.linalg.norm(axis), 1.):
            failures.append(f'{name}: malformed pin axis')
            continue
        axial = samples @ axis
        radial = np.linalg.norm(samples-axial[:, None]*axis, axis=1)
        expected_volume = np.pi*radius**2*length
        if (not mesh.is_volume or max(abs(axial.min()), abs(axial.max()-length)) > .02
                or abs(radial.max()-radius) > .02 or abs(mesh.volume/expected_volume-1.) > .02):
            failures.append(f'{name}: CAD does not match the declared smooth cylinder')
        homes = [host for host in entry['skip'] if host not in (name, f'{name}Retainer')]
        if len(homes) != 2:
            unknown.append(f'{name}: expected two documented mating parts')
            continue
        bearings[name] = {}
        for host in homes:
            radii = bore_radii(world.mesh(host), start, axis, length)
            proof = bore_span(radii, 2.075/2, 2.105/2)
            if proof is None:
                failures.append(f'{name}/{host}: no coaxial Ø2.08–2.10 finished bearing span in CAD')
            else:
                bearings[name][host] = proof
        cap = f'{name}Retainer'
        if types.get(cap, {}).get('kind') != 'set_screw':
            unknown.append(f'{name}: installed M3 stop is missing')
            continue
        ring = .9*transverse_vectors(axis)
        initial = np.asarray(start) + ring
        shoulder = ray_distances(world.mesh(homes[0]), initial, np.tile(-axis, (len(ring), 1)))
        retained = ray_distances(world.mesh(cap), initial+length*axis, np.tile(axis, (len(ring), 1)))
        if not np.isfinite(np.r_[shoulder, retained]).all() or min(shoulder.min(), retained.min()) < .01:
            failures.append(f'{name}: axial stops missing or contacting the nominal pin')
            continue
        float_mm = float(shoulder.min() + retained.min())
        axial_floats[name] = round(float_mm, 3)
        if not .18 <= float_mm <= .22:
            failures.append(f'{name}: CAD axial float {float_mm:.3f} mm disagrees with the 0.20 mm design')
    if report.get('cad_sha256') != digest:
        unknown.append('No measured B21 link bores tied to this CAD')
    else:
        blink = report.get('blink', {}).get('links', [])
        eyes = report.get('eye_links', {})
        profiles = dict(zip(('blink drive', 'left lid', 'right lid'), blink))
        profiles.update((name, eyes[name]) for name in ('pitch', 'yaw_left', 'yaw_right') if name in eyes)
        if len(profiles) != 6:
            unknown.append('Missing one or more link sections')
        for name, profile in profiles.items():
            bores = profile.get('sampled_bore_min_diameters_mm', ())
            if len(bores) != 2 or not all(np.isfinite(bores)):
                unknown.append(f'{name}: bore dimensions unavailable')
            elif min(bores) < 2.075 or max(bores) > 2.105:
                failures.append(f'{name}: CAD bores {list(bores)} exceed finished Ø2.08–2.10 mm fit with mesh allowance')
    return outcome('smooth_pivot_fit', failures=failures, unknown=unknown, mating_bores=bearings,
                   axial_float_mm=axial_floats,
                   scope='CAD finished sizes and smooth pin geometry; machining fit remains a physical inspection')


def assembly_check(rows, plan, digest, revision='b21'):
    failures, unknown = [], []
    if not rows or rows[0].get('cad_sha256') != digest:
        unknown.append('Assembly report is absent or identifies a different CAD source')
    if not rows or rows[0].get('plan_sha256') != plan_hash(plan):
        unknown.append('Assembly report identifies a different assembly plan')
    expected = [row['id'] for row in plan]
    if [row['id'] for row in rows] != expected:
        unknown.append('Assembly report does not cover the full ordered plan')
    else:
        for current, planned in zip(rows, plan, strict=True):
            stage = current['id']
            if current['text'] != planned['text'] or current['context'] != planned['ctx']:
                unknown.append(f'{stage}: checked step differs from plan')
            failures.extend(f'{stage}: {issue}' for issue in current['issues'] if not issue.endswith(' route unknown'))
            insertions = {'head-frame': 'head_frame_clearance', 'pitch-stop-link': 'pitch_link_clearance'}
            if revision == 'b22' and stage in insertions:
                clearance = current.get(insertions[stage], {}).get('continuous_lower_bound_mm')
                if clearance is None:
                    unknown.append(f'{stage}: missing continuous insertion clearance evidence')
                elif not np.isfinite(clearance) or clearance <= 0:
                    failures.append(f'{stage}: no continuous insertion clearance')
            if stage in ('lid-left', 'lid-right') and 'place2' in planned:
                clearance = current.get('lid_insertion_clearance', {}).get('continuous_lower_bound_mm')
                if clearance is None or not np.isfinite(clearance) or clearance < .20:
                    unknown.append(f'{stage}: missing clear complete eyelid insertion')
            if 'integral_print' in planned and current.get('integral_print') != planned['integral_print']:
                unknown.append(f'{stage}: missing declaration of single printed body')
            if revision == 'b22' and stage == 'jaw-bearing-fit':
                bearing = current.get('bearing_insertion', {})
                if bearing.get('status') != 'pass' or bearing.get('swept_overlap_mm3', np.inf) > 1e-7:
                    unknown.append(f'{stage}: missing clear complete bearing insertion')
            if 'camera_feed' in planned:
                feed = current.get('camera_feed', {})
                if (feed.get('status') != 'pass' or
                        any(feed.get(key) != value for key, value in planned['camera_feed'].items())):
                    unknown.append(f'{stage}: missing clear complete camera feed')
            if stage in B22_CAMERA_PATH_CHECKS:
                field, reserves = B22_CAMERA_PATH_CHECKS[stage]
                _, points = planned['path']
                legs = current.get(field, [])
                if [(tuple(leg.get('start_mm', ())), tuple(leg.get('end_mm', ()))) for leg in legs] != [
                        (tuple(start), tuple(end)) for start, end in zip(points, points[1:])]:
                    unknown.append(f'{stage}: missing complete camera insertion evidence')
                elif any(not np.isfinite(leg.get('continuous_lower_bound_mm', -np.inf)) or
                         leg['continuous_lower_bound_mm'] <= 0 or leg['continuous_lower_bound_mm'] < reserve
                         for leg, reserve in zip(legs, reserves, strict=True)):
                    failures.append(f'{stage}: insufficient continuous camera insertion clearance')
            if stage == 'camera-tray-bolts':
                heads = current.get('camera_tray_head_passage', {})
                for name in planned['bolts']:
                    if heads.get(name, {}).get('status') != 'pass':
                        unknown.append(f'{stage}/{name}: missing clear continuous socket head passage')
            for name in planned.get('hold_nuts', ()):
                access = current.get('tool_access', {}).get(name, {})
                if access.get('status') == 'fail':
                    failures.append(f'{stage}/{name}: no swept holding-tool route')
                elif access.get('status') != 'pass':
                    unknown.append(f'{stage}/{name}: no holding-tool route evidence')
            for name in planned.get('bolts', ()):
                access = current.get('driver_access', {}).get(name, {})
                if access.get('status') != 'pass':
                    unknown.append(f'{stage}/{name}: no qualified key route')
            for first, second in planned.get('paired_nuts', ()):
                pair = f'{first}/{second}'
                status = current.get('paired_tool_access', {}).get(pair, {}).get('status')
                if status == 'fail':
                    failures.append(f'{stage}/{pair}: tools cannot be seated together')
                elif status != 'pass':
                    unknown.append(f'{stage}/{pair}: no evidence of two-tool access')
            for nut, bolt in planned.get('paired_drivers', ()):
                pair = f'{nut}/{bolt}'
                status = current.get('paired_driver_access', {}).get(pair, {}).get('status')
                if status == 'fail':
                    failures.append(f'{stage}/{pair}: spanner and key interfere')
                elif status != 'pass':
                    unknown.append(f'{stage}/{pair}: no evidence of simultaneous spanner/key access')
            checked_angles = {entry['blink_deg']: entry['status'] for entry in current.get('blink_access_cases', ())}
            for angle in planned.get('blink_access_checks_deg', ()):
                if checked_angles.get(angle) != 'pass':
                    unknown.append(f'{stage}: missing supplemental pin/key clearance at {angle:g}°')
    return outcome('assembly_path_and_tools', failures=failures, unknown=unknown, steps=len(rows))


def rigid_motion_check(report, digest):
    if report.get('cad_sha256') != digest or report.get('pose_samples', 0) < 26408 or 'collisions' not in report:
        return outcome('rigid_motion', unknown=['No complete B21 motion sweep bound to this CAD'])
    return outcome('rigid_motion', failures=[str(pair) for pair in report['collisions']],
                   sampled_poses=report['pose_samples'])


def light_touch_check(report, digest):
    if report.get('cad_sha256') != digest:
        return outcome('light_touch', unknown=['No light-touch report bound to this CAD'])
    cases = {tuple(row['contact_force_per_lid_N']): row for row in report.get('rigid_pin_drag_cases', ())
             if row.get('mode') in ('closing_touch', 'intrinsic_drag_only')}
    failures, unknown = [], []
    for case in sorted(CHECKED_LIGHT_CASES):
        row = cases.get(case, {})
        requirements = ('min_closed_end_deg', 'max_return_end_error_deg', 'torque_saturated', 'contact_count')
        if not all(key in row for key in requirements):
            unknown.append(f'{case}: missing endpoint, saturation or contact data')
        elif (row['min_closed_end_deg'] < 87.5 or row['max_return_end_error_deg'] > 2.5
              or row['torque_saturated'] or row['contact_count']):
            failures.append(f'{case}: closure, return, saturation or contact outside modelled limits')
    return outcome('light_touch', failures=failures, unknown=unknown, cases=len(cases),
                   scope='numerical joint/load model, not measured servo output or printed durability')


def run(cad, source, hardware, spec, bom, assembly, head, touch, revision='b21'):
    digest = sha256(source.read_bytes()).hexdigest()
    layout = read(cad/'cad_parts.json')
    plan = assembly_plan(revision, layout)
    if layout['source_sha256'] != digest:
        return [outcome('cad_source', unknown=['CAD export hash does not match source'])]
    entries = read(hardware)['hardware']
    parts = read(spec)
    world = World(cad, entries, parts)
    checks = []
    for name, function in (
        ('fastener_stock', lambda: installed_fasteners(plan, world, layout, parts, bom)),
        ('assembly_path_and_tools', lambda: assembly_check(read(assembly), plan, digest, revision)),
        ('rigid_motion', lambda: rigid_motion_check(read(head), digest)),
        ('smooth_pivot_fit', lambda: pivot_check(plan, world, parts, read(touch), digest)),
        ('light_touch', lambda: light_touch_check(read(touch), digest)),
    ):
        try:
            checks.append(function())
        except (OSError, ValueError, KeyError, TypeError) as error:
            checks.append(outcome(name, unknown=[str(error)]))
    return checks


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    for name in ('cad', 'source', 'hardware', 'spec', 'bom', 'assembly', 'head', 'touch', 'report'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    parser.add_argument('--revision', choices=('b21', 'b22'), default='b21')
    args = vars(parser.parse_args())
    target = args.pop('report')
    try:
        results = run(**args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        results = [outcome('release_inputs', unknown=[str(error)])]
    report = {'status': 'fail' if any(row['status'] == 'fail' for row in results) else
              'unknown' if any(row['status'] == 'unknown' for row in results) else 'pass', 'checks': results}
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    if report['status'] != 'pass':
        raise SystemExit(1)
