"""Build the purchased connector geometry used by the B15 review."""

from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
import json
import sys

import FreeCAD as App
from FreeCAD import Vector as V
import MeshPart
import numpy as np
import Part
import trimesh

HERE = Path(__file__).resolve().parent
MECHANICAL = HERE.parent / 'mechanical'
sys.path[:0] = [str(MECHANICAL), str(MECHANICAL / 'physics')]
from export_cad import world_shape
from fixtures import CABLE_CENTER_Z, CABLE_LANES, CABLE_STOP_Y
from primitives import box, cylinder

AMASS_XT30 = 'https://www.china-amass.com/public/upload/20240608/810c62b3f7ace2287989748538eb2a6b.pdf'
AMASS_XT60 = 'https://www.china-amass.com/public/upload/20240620/94b600a6a4c042646bc89646abc8ea85.pdf'
STARTECH = 'https://media.startech.com/downloads/image/USBEXTAA6IN_Diagram.pdf'
JST_PH = 'https://www.jst-mfg.com/product/index.php?lang=en&series=199'
JST_EH = 'https://www.jst-mfg.com/product/index.php?lang=2&series=58'
KICAD_JST = 'https://github.com/KiCad/kicad-packages3D/tree/master/Connector_JST.3dshapes'
REAR = CABLE_STOP_Y - .08
USB_REAR = REAR + 5.6
USB_MOUTH = USB_REAR - 39.5 - 9.5
TAIL_Y = REAR + 22.85
COLORS = {
    'xt': ((243, 177, 37), 0., .42),
    'brass': ((210, 163, 70), .63, .29),
    'steel': ((182, 196, 205), .76, .28),
    'rubber': ((40, 46, 52), 0., .67),
    'red': ((215, 62, 49), 0., .56),
    'black': ((39, 44, 52), 0., .58),
    'white': ((222, 223, 211), 0., .56),
    'nylon': ((223, 223, 204), 0., .47),
}


def face_profile(y, width, height, bevel, key=0.):
    w, h = width / 2, height / 2
    points = [
        (-w, -h + bevel), (-w + bevel, -h), (w - bevel - key, -h),
        (w, -h + bevel + key), (w, h - bevel - key), (w - bevel - key, h),
        (-w + bevel, h), (-w, h - bevel),
    ]
    vertices = [V(x, y, z) for x, z in points]
    return Part.makePolygon(vertices + vertices[:1])


def profile_body(stations, key=0.):
    return Part.makeLoft([face_profile(*station, key=key) for station in stations], True, True)


def shift(parts, x, y, z):
    return [(material, shape.copy().translate(V(x, y, z))) for material, shape in parts]


def at_basis(parts, origin, row, rear):
    x, y = V(*row), V(*rear)
    z = x.cross(y)
    rotation = App.Rotation(x, y, z, 'XYZ')
    return [(material, shape.copy().rotate(V(), rotation.Axis, rotation.Angle * 180 / np.pi)
             .translate(V(*origin))) for material, shape in parts]


def xt_pigtails(pitch, direction, pin_tip, tail, outside_d, wire_d):
    items = []
    for index, material in enumerate(('black', 'red')):
        x = (index - .5) * pitch
        span = abs(tail - pin_tip)
        axis = (0, direction, 0)
        boot = min(8., span / 2)
        items.append(('rubber', cylinder(outside_d / 2, boot, (x, pin_tip, 0), axis)))
        items.append((material, cylinder(wire_d / 2, span - boot, (x, pin_tip + direction * boot, 0), axis)))
    return items


def xt30_pair():
    # AMASS gives 10.2 x 5.6 at each body and 12.4 / 13.7 over the terminations.
    female = profile_body([(-9.6, 9.75, 5.3, .34), (-7., 9.75, 5.3, .34),
                           (-6.6, 10.2, 5.6, .38), (-.32, 10.2, 5.6, .38),
                           (0., 9.78, 5.42, .38)], key=1.12)
    male = profile_body([(-14.5, 9.72, 5.36, .38), (-14.1, 10.2, 5.6, .38),
                         (-8.12, 10.2, 5.6, .38), (-7.85, 9.88, 5.42, .36)], key=1.12)
    clearance = profile_body([(-9.61, 9.85, 5.38, .31), (-7.83, 9.85, 5.38, .31)], key=1.08)
    male = male.cut(clearance)
    pieces = [('xt', female), ('xt', male)]
    for x in (-2.5, 2.5):
        pieces.extend([
            ('brass', cylinder(1.0, 2.8, (x, 0., 0.), (0, 1, 0))),
            ('brass', cylinder(1.0, 2.8, (x, -14.5, 0.), (0, -1, 0))),
        ])
    tails = xt_pigtails(5., 1, 2.65, TAIL_Y-REAR, 4., 2.057)
    tails += xt_pigtails(5., -1, -17.15, -21., 4., 2.057)
    return pieces + tails


def xt60(path, female):
    step = Part.read(str(path))
    if not step.isValid() or not step.Solids:
        raise ValueError(f'Invalid source STEP {path}')
    bound = step.BoundBox
    if abs(bound.XLength - 15.30) > .02 or abs(bound.YLength - 7.90) > .02 or abs(bound.ZMax - 13.50) > .02:
        raise ValueError(f'{path.name} disagrees with the AMASS body dimensions')
    housing = step.common(box(-10, 10, -6, 6, 0, 14))
    contacts = step.common(box(-10, 10, -6, 6, -5, 0))
    direction = 1 if female else -1
    transformed = [(material, shape.rotate(V(), V(1, 0, 0), direction * 90))
                   for material, shape in [('xt', housing), ('brass', contacts)]]
    tail = TAIL_Y - REAR if female else 75.32 - 99.
    return transformed + xt_pigtails(7.2, direction, direction * 3.59, tail, 5.6, 3.023)


def usb_a():
    # Drawing dimensions: 39.5 mm from the boot exit to the front of the
    # 16 x 9.1 mm overmold. The 14.5 x 7.2 mm metal shell extends 9.5 mm.
    mold = profile_body([(-39.5, 15.45, 8.55, .56), (-39.05, 16., 9.1, .62),
                         (-16.8, 16., 9.1, .62), (-13., 11.8, 9.1, .68),
                         (-6., 11.8, 9.1, .71), (-5.6, 11.1, 8.45, .66)])
    boot = profile_body([(-5.65, 6.65, 5.55, 1.2), (0., 5.6, 5.25, 1.65)])
    shell = profile_body([(-49., 14.5, 7.2, .48), (-39.3, 14.5, 7.2, .46)]).cut(
        profile_body([(-49.05, 12.6, 5.1, .24), (-39.25, 12.6, 5.1, .22)]))
    pieces = [('rubber', mold), ('rubber', boot), ('steel', shell),
              ('black', box(-5.75, 5.75, -48.15, -39.2, .43, 2.29)),
              ('black', cylinder(2.4, TAIL_Y-USB_REAR+.02, (0, -.02, 0), (0, 1, 0)))]
    for y in (-5.2, -3.75, -2.3, -.85):
        pieces.append(('rubber', profile_body([(y, 6.58, 5.58, 1.02),
                                               (y + .51, 6.58, 5.58, 1.02)])))
    for x in (-3.75, -1.25, 1.25, 3.75):
        pieces.append(('brass', box(x-.42, x+.42, -47.65, -42.25, .36, .45)))
    return pieces


def jst_housing(count, pitch, width, height, length):
    housing = profile_body([(-length, width-.4, height-.36, .26),
                            (-length+.44, width, height, .31), (-.40, width, height, .31),
                            (0., width-.4, height-.34, .27)])
    centres = [(index - (count-1)/2) * pitch for index in range(count)]
    recesses = [box(x-.59, x+.59, -length-.05, .05, -.67, .67) for x in centres]
    clips = [box(x-.40, x+.40, -length+1.5, -1., height*.28, height/2+.05) for x in centres]
    return [('nylon', housing.cut(recesses+clips)),
            ('nylon', box(-width*.33, width*.33, -length+1.15, -length+2.4, height*.45, height/2+.32))]


def hub_reference(cad, port):
    centre = world_shape(cad.getObject(f'HubPlugJ{port}')).BoundBox.Center
    pitch = 2. if port <= 6 else 2.5
    count = 2 if port == 3 else 3
    width = 5.8 if count == 2 else 7.8 if port <= 6 else 9.5
    depth, length = (4.5, 6.85) if port <= 6 else (3.8, 7.1)
    pieces = jst_housing(count, pitch, width, depth, length)
    colors = ('black', 'white') if count == 2 else ('black', 'red', 'white')
    for index, color in enumerate(colors):
        x = (index - (count-1)/2) * pitch
        pieces.append((color, cylinder(1.143 / 2, 4.05, (x, -.05, 0), (0, 1, 0))))
    return at_basis(pieces, (centre.x, centre.y, -60.5), (1, 0, 0), (0, 0, 1))


def hub_header(cad, port, inputs):
    if port <= 6:
        count = 2 if port == 3 else 3
        filename = f'JST_PH_B{count}B-PH-K_1x0{count}_P2.00mm_Vertical.step'
    else:
        filename = 'JST_EH_B3B-EH-A_1x03_P2.50mm_Vertical.step'
    step = Part.read(str(inputs/filename))
    if not step.isValid() or not step.Solids:
        raise ValueError(f'Invalid source STEP {filename}')
    centre = world_shape(cad.getObject(f'HubBodyJ{port}')).BoundBox.Center
    top = world_shape(cad.HubPCB).BoundBox.ZMax
    source = step.BoundBox.Center
    housing = step.common(box(-12, 12, -8, 8, 0, 8))
    leads = step.common(box(-12, 12, -8, 8, -5, 0))
    return shift([('nylon', housing), ('brass', leads)], centre.x-source.x, centre.y-source.y, top)


def fit_report(cad, pieces):
    rigid = ('Part000', 'CableSaddle', 'CableGate', 'HubHolder', 'HubBodyJ1', 'HubBodyJ2')
    obstacles = {name: world_shape(cad.getObject(name)) for name in rigid}
    for id in ('InputXT30', 'InputXT60', 'InputXT60Mate', 'CameraUSB', 'ControlUSB'):
        shape = Part.Compound([s for _, s in pieces[id]])
        overlaps = {name: round(shape.common(s).Volume, 3) for name, s in obstacles.items()
                    if shape.BoundBox.intersect(s.BoundBox)}
        print(id, overlaps, flush=True)
    female = Part.Compound([s for color, s in pieces['InputXT60'] if color in ('xt', 'brass')])
    for offset in (16., 12., 8., 4., 0.):
        male = Part.Compound([s.copy().translate(V(0, -offset, 0)) for color, s in pieces['InputXT60Mate']
                              if color in ('xt', 'brass')])
        volumes = [male.common(s).Volume for s in [female, *obstacles.values()] if male.BoundBox.intersect(s.BoundBox)]
        if max(volumes, default=0.) > .03:
            raise ValueError(f'XT60U-M insertion collides at {offset:g} mm')
    print('XT60U-M insertion: five poses clear against the XT60U-F and tray.', flush=True)


def linear_color(rgb):
    srgb = np.array(rgb, dtype=float) / 255.
    linear = ((srgb+.055) / 1.055) ** 2.4
    return (*np.round(255*np.where(srgb <= .04045, srgb / 12.92, linear)).astype(np.uint8), 255)


def export(cad_path, inputs, out, review_cad):
    doc = App.openDocument(str(cad_path.resolve()))
    try:
        x30, x60, cam, ctl = (lane[1] for lane in CABLE_LANES)
        usb = usb_a()
        pieces = {
            'InputXT30': shift(xt30_pair(), x30, REAR, CABLE_CENTER_Z),
            'InputXT60': shift(xt60(inputs/'XT60U-F.step', True), x60, REAR, CABLE_CENTER_Z),
            'InputXT60Mate': shift(xt60(inputs/'XT60U-M.step', False), x60, 99., CABLE_CENTER_Z),
            'CameraUSB': shift(usb, cam, USB_REAR, CABLE_CENTER_Z),
            'ControlUSB': shift(usb, ctl, USB_REAR, CABLE_CENTER_Z),
        }
        info = {
            'InputXT30': ('5 V · XT30U 암수', 'AMASS 도면', AMASS_XT30),
            'InputXT60': ('목 전원 · XT60U-F', '공급사 STEP', 'https://www.lcsc.com/product-detail/C19191801.html'),
            'InputXT60Mate': ('목 전원 · XT60U-M', '공급사 STEP', 'https://www.lcsc.com/product-detail/C129184.html'),
            'CameraUSB': ('카메라 · USB-A 연장선', 'StarTech 도면', STARTECH),
            'ControlUSB': ('OpenRB · USB-A 연장선', 'StarTech 도면', STARTECH),
        }
        for port in range(3, 9):
            id = f'HubPlugJ{port}'
            pieces[id] = hub_reference(doc, port)
            model = 'PHR-2' if port == 3 else 'PHR-3' if port <= 6 else 'EHR-3'
            info[id] = (f'J{port} · JST {model}', 'JST 도면', JST_PH if port <= 6 else JST_EH)
            header = f'HubBodyJ{port}'
            pieces[header] = hub_header(doc, port, inputs)
            model = 'B2B-PH-K-S' if port == 3 else 'B3B-PH-K-S' if port <= 6 else 'B3B-EH-A'
            info[header] = (f'J{port} · JST {model}', 'KiCad STEP', KICAD_JST)
        eh = jst_housing(3, 2.5, 9.5, 3.8, 7.1)
        for label, origin, row, direction in (
            ('ID1EH', (3.2, -22.9, 93.55), (1, 0, 0), (0, 1, 0)),
            ('ID2EH', (40.35, -2.6, 142.), (0, 0, 1), (0, -1, 0)),
            ('ID3EH', (-17.1, -1.4, 179.), (0, 0, 1), (0, 1, 0)),
            ('ID4EH', (-16.85, 14.1, -62.1), (0, 1, 0), (-1, 0, 0)),
            ('ID5EH', (11.8, -16.85, 97.9), (0, 0, 1), (0, -1, 0)),
            ('ID6EH', (-25.5, 3.6, 101.), (0, 0, 1), (0, 1, 0)),
            ('OpenRBEH', (34.4, -25., -65.5), (0, 1, 0), (-1, 0, 0)),
        ):
            pieces[label] = at_basis(eh, origin, row, direction)
            info[label] = (f'{label.replace("EH", "")} · JST EHR-3', 'JST 도면', JST_EH)
        fit_report(doc, pieces)
        scene = trimesh.Scene()
        materials = {key: trimesh.visual.material.PBRMaterial(name=key, baseColorFactor=linear_color(rgb),
                     metallicFactor=metallic, roughnessFactor=rough) for key, (rgb, metallic, rough) in COLORS.items()}
        for id, shapes in pieces.items():
            scene.graph.update(frame_to=id, matrix=np.eye(4))
            for color in sorted({key for key, s in shapes}):
                solids = Part.Compound([shape for key, shape in shapes if key == color])
                mesh = MeshPart.meshFromShape(Shape=solids, LinearDeflection=.045, AngularDeflection=.17, Relative=False)
                vertices, triangles = mesh.Topology
                surface = trimesh.Trimesh(vertices=np.array([tuple(v) for v in vertices]), faces=np.array(triangles))
                surface = surface.smooth_shaded
                surface.visual = trimesh.visual.TextureVisuals(material=materials[color])
                scene.add_geometry(surface, parent_node_name=id, node_name=f'{id}_{color}', geom_name=f'{id}_{color}')
        out.mkdir(parents=True, exist_ok=True)
        (out/'connectors.glb').write_bytes(trimesh.exchange.gltf.export_glb(scene, include_normals=True))
        metadata = {'cad_sha256': sha256(cad_path.read_bytes()).hexdigest(), 'parts': {
            id: {'name': name, 'source': source, 'url': url} for id, (name, source, url) in info.items()}}
        (out/'connectors.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n')
        if review_cad:
            for id, parts in pieces.items():
                reference = doc.getObject(id)
                if reference is not None:
                    compound = Part.Compound([shape for _, shape in parts])
                    compound.Placement = reference.getGlobalPlacement().inverse()
                    reference.Shape = compound
                    reference.Label = f'구매품 · {info[id][0]}'
            doc.R5.Label = 'R5 B15 · 구매품 참고'
            review_cad.parent.mkdir(parents=True, exist_ok=True)
            doc.recompute()
            doc.saveAs(str(review_cad.resolve()))
        print(f'{len(info)} connector placements. USB receptacle face at y={USB_MOUTH:.2f} mm.', flush=True)
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('steps', type=Path)
    parser.add_argument('--output', type=Path, default=HERE/'assets')
    parser.add_argument('--review-cad', type=Path)
    args = parser.parse_args()
    export(args.cad, args.steps, args.output, args.review_cad)
