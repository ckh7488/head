"""Export the B25 motion demo without changing the archived assembly viewer."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

import FreeCAD as App
import Mesh  # Register Mesh::Feature before opening the document.
import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT / 'mechanical/physics'), str(ROOT / 'mechanical'), str(ROOT / 'control/verification')]
from check_b25_camera_lower import CUT_LENGTH, DATA, REAR_RADIUS, lower_bight
from check_b25_camera_upper import upper_at
from check_b25_j2_a4_service import LEADS, service_route
from check_b25_j2_disconnect import DROP, PARK, WITHDRAW, WIRE_RADIUS
from check_b25_jaw_opening import CLOSED_REFERENCE_TICKS
from export_cad import world_shape
from wiring_motion import rotation, transform

COLORS = {
    'bone': (220, 204, 177), 'jaw': (214, 198, 169), 'graphite': (56, 66, 70),
    'shroud': (37, 44, 47), 'steel': (139, 153, 161), 'link': (164, 117, 65),
    'frame': (93, 142, 130), 'gear': (44, 50, 56), 'eye': (228, 232, 218),
    'iris': (77, 123, 103), 'pupil': (12, 17, 17), 'glass': (29, 41, 50),
    'pcb': (48, 106, 76), 'connector': (194, 196, 180), 'power': (225, 171, 51),
    'terminal': (85, 145, 107), 'fuse': (181, 92, 67), 'capacitor': (112, 114, 117),
    'brass': (174, 128, 65), 'red_wire': (220, 68, 54), 'black_wire': (54, 63, 69),
    'camera_wire': (54, 167, 191), 'control_wire': (92, 124, 170),
}
TICK_DEG = 360. / 4096.
AXIS_LIMITS = {'yaw': 640*TICK_DEG, 'pitch': [-149*TICK_DEG, 30*TICK_DEG]}
MOTORS = {'Part017', 'Part018', 'Part038', 'Part041', 'Part045', 'Jaw_XL330_M288_Jaw'}
OMIT = {'Part065', 'Part070', 'Part071', 'EatonCableNeutral', *LEADS}
WIRE_COLORS = {
    'RearLead1_1': 'red_wire', 'RearLead1_2': 'black_wire', 'RearLead3_1': 'camera_wire',
    'RearLead4_1': 'control_wire', 'A4W6': 'red_wire', 'A4W35': 'red_wire',
    'A4W7': 'black_wire', 'A4W36': 'black_wire', 'CameraEatonHeadFixedLeg': 'camera_wire',
    'CameraOEMHeadTail': 'camera_wire', 'CameraEatonHeadSplice': 'black_wire',
    'EatonRearStationarySplice': 'black_wire',
}


def include(name):
    return name not in OMIT and not name.lower().startswith(('hubrearclearance', 'c3', 'ballast'))


def style(name, label, existing):
    if name in WIRE_COLORS:
        return WIRE_COLORS[name]
    if name.endswith('Insert'):
        return 'brass'
    if name.startswith(('A4Wago', 'A4J2LeverKeeper')):
        return 'terminal'
    if 'Cup' in name:
        return 'brass'
    if 'XT60' in name or name.startswith('SupplyXT30'):
        return 'power'
    if name.startswith(('A4J1', 'A4J2', 'Harness', 'Input', 'ID5EH')):
        return 'connector'
    if re.search(r'screw|bolt|nut|retainer|pin|shim|collar|fastener', name, re.I):
        return 'steel'
    if name.startswith('CableTie') or name.endswith('Tie'):
        return 'black_wire'
    return existing.get('finish', 'link' if 'link' in label.lower() else 'graphite')


def resample(points, count):
    points = np.asarray(points)
    stations = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    distances = np.linspace(0, stations[-1], count)
    return np.column_stack([np.interp(distances, stations, coordinate) for coordinate in points.T])


def packed(points):
    return np.round(points, 3).tolist()


def eaton():
    controls = json.loads(DATA.read_text())
    anchor = np.array(controls['anchor_mm'])
    heading = np.radians(controls['fixed']['heading_deg'])
    turn = np.array(((np.cos(heading), np.sin(heading), 0.),
                     (-np.sin(heading), np.cos(heading), 0.), (0., 0., 1.)))
    lower = []
    for angle in np.linspace(-AXIS_LIMITS['yaw'], AXIS_LIMITS['yaw'], 41):
        datum = transform([0., -36.75, controls['rotor_entry_z_mm']], rotation(-angle, (0, 0, 1)))
        points, _ = lower_bight(anchor @ turn, datum @ turn)
        lower.append(packed(resample(points @ turn.T, 73)))
    upper = [packed(resample(upper_at(angle, 0.)[0], 97))
             for angle in np.linspace(*AXIS_LIMITS['pitch'], 25)]
    return {'cut_mm': CUT_LENGTH, 'return_radius_mm': REAR_RADIUS,
            'fixed': packed(resample(controls['fixed']['curve_mm'][::-1], 134)),
            'yaw_range': [-AXIS_LIMITS['yaw'], AXIS_LIMITS['yaw']], 'lower_yaw': lower,
            'pitch_range': AXIS_LIMITS['pitch'], 'upper_pitch': upper}


def service_pose(progress):
    return (WITHDRAW * min(1., progress * 4.), PARK * np.clip(progress * 4. - 1., 0., 1.),
            DROP * max(0., 2. * progress - 1.))


def service_leads():
    paths = {key: [] for key in LEADS}
    for progress in np.linspace(0., 1., 33):
        pose = service_pose(progress)
        for name, coordinates in LEADS.items():
            edges, _ = service_route(*coordinates, *pose)
            curve = [tuple(v) for e in edges for v in e.discretize(Number=max(2, int(e.Length) + 1))[:-1]]
            curve.append(tuple(edges[-1].Vertexes[-1].Point))
            paths[name].append(packed(resample(curve, 96)))
    return {'withdrawal_mm': WITHDRAW, 'parking_mm': PARK, 'drop_mm': DROP, 'paths': paths,
            'diameter': 2 * WIRE_RADIUS}


def wire_frames(name, points):
    start_on_hatch = (re.match(r'motor[1235]-(return|power|data)$', name) and name != 'motor3-data') or name == 'J6-branch'
    stations = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    length = stations[-1]
    result = []
    for station, (x, y, z) in zip(stations, points, strict=True):
        xyz = [round(float(p), 3) for p in (x,y,z)]
        if name in ('J1+', 'J1-'):
            progress = float(np.clip((station - length + 55.) / 30., 0., 1.))
            xyz.extend(('fixed', 'hatch', round(progress, 3)))
        elif start_on_hatch and station < 36.:
            xyz.extend(('hatch', 'fixed', round(float(np.clip((station - 8.) / 28., 0., 1.)), 3)))
        elif name.startswith('motor'):
            if z < -56. or y > 12. and z < -44.:
                result.append(xyz)
                continue
            if z < -40.:
                xyz.extend(('fixed', 'pan', round((z + 56.) / 16., 3)))
            elif name.startswith('motor5-') or z < 59.:
                xyz.append('pan')
            elif z < 83.:
                xyz.extend(('pan', 'head', round((z - 59.) / 24., 3)))
            elif name.startswith('motor1-') and z > 80.:
                xyz.extend(('head', 'tilt', round(float(np.clip((z - 82.) / 14., 0., 1.)), 3)))
            else:
                xyz.append('head')
        result.append(xyz)
    return result


def deviation(reduced, original, samples=4000):
    worst = 0.
    for a, b in ((reduced, original), (original, reduced)):
        points = trimesh.sample.sample_surface(a, samples, seed=1)[0]
        _, distance, _ = trimesh.proximity.closest_point(b, points)
        worst = max(worst, float(np.max(distance)))
    return worst


def faithful_reduction(mesh, limit, allowed):
    for target in [t for t in (limit, 2*limit, 4*limit) if t < len(mesh.faces)]:
        reduced = mesh.simplify_quadric_decimation(face_count=target)
        if mesh.is_watertight and not reduced.is_watertight:
            continue
        if deviation(reduced, mesh) <= allowed:
            return reduced
    return mesh


def native_wires(doc):
    wires = []
    for obj in doc.WiringRouting.Group:
        if not obj.Name.startswith('HarnessWire') or obj.Name == 'HarnessWire015':
            continue
        name = obj.Label.split('·')[0].strip()
        points = np.array([list(v.Point) for v in world_shape(obj).Vertexes])
        if len(points) < 2:
            continue
        diameter = obj.JacketDiameter.Value
        length = np.linalg.norm(np.diff(points, axis=0), axis=1).sum()
        path = resample(points, min(151, max(2, 1 + int(length / 2))))
        kind = 'power' if name.endswith(('+', '-power')) or name == 'fuse-in' else 'return' if name.endswith(('-', '-return')) else 'data'
        wires.append({'id': obj.Name, 'label': name, 'kind': kind, 'diameter': diameter,
                      'baseOnly': not name.startswith('motor'), 'sampled': True,
                      'points': wire_frames(name, path)})
    return wires


def build(assembly, cad, output):
    layout = json.loads((cad / 'cad_parts.json').read_text())
    digest = sha256(assembly.read_bytes()).hexdigest()
    if digest != layout['source_sha256']:
        raise ValueError('The viewer meshes are from another assembly revision')
    archived = {entry['cad_id']: entry for entry in json.loads((HERE/'assets/assembly.json').read_text())['parts']}
    doc = App.openDocument(str(assembly.resolve()))
    try:
        wires = native_wires(doc)
        materials = {name: trimesh.visual.material.PBRMaterial(
            name=name, baseColorFactor=np.array((*color, 255), dtype=np.uint8),
            roughnessFactor=.60, metallicFactor=.42 if name in ('steel','brass') else 0.)
            for name, color in COLORS.items()}
        scene = trimesh.Scene()
        parts = []
        for name, role in layout['world_motion'].items():
            file = cad / 'world' / f'{name}.stl'
            if not include(name) or file.stat().st_size <= 84:
                continue
            data = file.read_bytes()
            if sha256(data).hexdigest() != layout['world_sha256'][name]:
                raise ValueError(f'The exported mesh changed for {name}')
            previous = archived.get(name, {})
            label = doc.getObject(name).Label
            finish = style(name, label, previous)
            mesh = trimesh.load_mesh(file)
            cap = 18000 if name in MOTORS else 36000 if previous.get('shell') else 8500 if name in ('Part000','Part019','CableSaddle','HubPCB') else 2600
            if len(mesh.faces) > cap:
                # Same rule as the assembly viewer: reduce only while the surface stays within
                # 0.05 mm (printed parts) or 0.3 mm (bought parts) of the CAD, else keep the CAD mesh.
                printed = re.match(r'\d{2}[ _]', label or '') or name == 'Part000'
                mesh = faithful_reduction(mesh, cap, .05 if printed else .3)
            if name in MOTORS:
                mesh = mesh.smooth_shaded
            mesh.visual = trimesh.visual.TextureVisuals(material=materials[finish])
            scene.add_geometry(mesh, node_name=name, geom_name=name)
            parts.append({'name': name, 'cad_id': name, 'label': label,
                          'motion': 'service_plug' if name=='A4XT60ExternalMate' else role,
                          'shell': bool(previous.get('shell')), 'cover': bool(previous.get('cover')),
                          'wire': name in WIRE_COLORS, 'finish': finish})
        output.mkdir(parents=True, exist_ok=True)
        (output/'assembly.glb').write_bytes(trimesh.exchange.gltf.export_glb(scene, include_normals=True))
        rig = {kind: layout['motion_geometry'][kind] for kind in ('eye_pitch','eye_yaw','blink','pitch_stop')}
        rig['jaw_pivot_mm'] = layout['jaw_pivot_mm']
        rig['jaw_closed_deg'] = CLOSED_REFERENCE_TICKS * TICK_DEG
        revision = 'B26' if layout['motion_geometry'].get('bottom_board_nut_seats') else 'B25'
        document = {'revision':revision,'board':'A5','cad_sha256':digest,'parts':parts,'rig':rig,
                    'wiring': {'routes':wires, 'blocks':[], 'eaton':eaton(), 'service':service_leads()}}
        (output/'assembly.json').write_text(json.dumps(document,ensure_ascii=False,separators=(',',':'))+'\n')
        print(f'{len(parts)} {document["revision"]} solids, {len(wires)} native wire centers · {digest[:12]}', flush=True)
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser=ArgumentParser(description=__doc__)
    for name in ('assembly','cad','output'):
        parser.add_argument(name,type=Path)
    build(**vars(parser.parse_args()))
