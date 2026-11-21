"""Build the independent B25 PETG HF fit-gauge plate from the frozen P2S profile."""

from argparse import ArgumentParser
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import FreeCAD as App
from FreeCAD import Vector as V
from lxml import etree
import Part
import trimesh

from build_b20_print import CORE, MODEL, MODEL_RELS, MODEL_SETTINGS, PRODUCTION, replace_mesh, serialize
from primitives import box, cylinder, print_mesh


B25 = Path(__file__).resolve().parent / 'revisions/b25'
SETTINGS = 'Metadata/project_settings.config'
# Diameters are modeled, before the specified 0.15 mm printing bias.
ROWS = (
    ('L2', 0., (2.45, 2.50, 2.55, 2.60, 2.65), 8., 4., 'horizontal'),
    ('M2', 13., (2.15, 2.20, 2.25, 2.30, 2.35), 8., 2.7, 'vertical'),
    ('M3', 26., (3.20, 3.30, 3.40, 3.50, 3.60), 8., 5., 'vertical'),
    ('H3', 40., (3.20, 3.30, 3.40, 3.50, 3.60), 9., 5., 'horizontal'),
    ('P3', 53., (3.14, 3.19, 3.24, 3.29, 3.34), 9., 5., 'horizontal'),
    ('P4', 67., (4.16, 4.21, 4.26, 4.31, 4.36), 9., 5., 'vertical'),
    ('H4', 82., (4.05, 4.10, 4.15, 4.20, 4.25), 10., 4.4, 'horizontal blind'),
    ('B6', 97., (6.05, 6.10, 6.15, 6.20, 6.25), 12., 2.55, 'shoulder'),
    ('B10', 113., (10.05, 10.10, 10.15, 10.20, 10.25), 14., 4.05, 'shoulder'),
    ('O2', 132., (2.30, 2.35, 2.40, 2.45, 2.50), 8., 4., 'horizontal'),
    ('P8', 146., (8.10, 8.15, 8.20, 8.25, 8.30), 13., 10., 'horizontal'),
    ('B16', 165., (16.10, 16.20, 16.30, 16.40, 16.50), 22., 9.5, 'horizontal shoulder'),
    ('S4', 184., (4.45, 4.50, 4.55, 4.60, 4.65), 9., 5., 'vertical'),
    ('V8', 199., (8.10, 8.15, 8.20, 8.25, 8.30), 13., 5., 'vertical'),
)
YAW_Y = 220.
YAW_DIAMETERS = (100.10, 100.20, 100.30, 100.40, 100.50)


def round_row(y, sizes, width, depth, direction):
    parts = []
    pitch = 1.2 * width
    # The rail leaves each hole accessible from both sides.
    for index, diameter in enumerate(sizes):
        x = 7. + pitch * index
        if direction.startswith('horizontal'):
            frame = box(x-width/2, x+width/2, y, y+depth+.28, 0., width)
            if direction.endswith('shoulder'):
                frame = box(x-width/2, x+width/2, y, y+depth+1.2, 0., width)
                bore = cylinder(diameter/2, depth+.2, (x, y+1.2, width/2), (0, 1, 0))
                bore = bore.fuse(cylinder(sizes[0]/2-.7, depth+.4, (x, y-.2, width/2), (0, 1, 0)))
            elif direction.endswith('blind'):
                frame = box(x-width/2, x+width/2, y, y+depth+2., 0., width)
                mouth = cylinder(diameter/2, depth+.2, (x, y-.2, width/2), (0, 1, 0))
                stop = cylinder(1.98, .5, (x, y+depth-.03, width/2), (0, 1, 0))
                bore = mouth.fuse(stop)
            else:
                bore = cylinder(diameter/2, depth+1., (x, y-.2, width/2), (0, 1, 0))
        else:
            shoulder = direction == 'shoulder'
            height = depth + (1.2 if shoulder else 0.)
            frame = box(x-width/2, x+width/2, y, y+width, 0., height)
            bore = cylinder(diameter/2, depth+.2, (x, y+width/2, height-depth if shoulder else -.1))
            if shoulder:
                through = cylinder(sizes[0]/2-.45, height+1., (x, y+width/2, -.2))
                bore = bore.fuse(through)
        parts.append(frame.cut(bore))
    strap = box(0., 7.+pitch*4+width/2, y-.95, y+.27, 0., 1.2)
    return strap.fuse(parts).removeSplitter()


def yaw_row():
    first = 12.
    width = 24.
    # An arc compares radial fit without implying that a short coupon measures roundness.
    tabs = []
    for index, diameter in enumerate(YAW_DIAMETERS):
        center = V(first+width*index, YAW_Y-48., 0.)
        outer = Part.makeCylinder(55., 12., center, V(0, 0, 1), 20.)
        outer.rotate(center, V(0, 0, 1), 80.)
        shoulder_clearance = cylinder(48.6, 13., (center.x, center.y, -.2))
        seat = cylinder(diameter/2, 11.2, (center.x, center.y, 1.0))
        tabs.append(outer.cut([shoulder_clearance, seat]))
    rail = box(0., first+width*4+10., YAW_Y+5.5, YAW_Y+7.4, 0., 1.1)
    return rail.fuse(tabs).removeSplitter()


def gauge_shape():
    rows = [round_row(y, sizes, width, depth, direction) for _, y, sizes, width, depth, direction in ROWS]
    rows.append(yaw_row())
    edge = box(-1.4, .45, -1., YAW_Y+6.1, 0., 1.2)
    plate = edge.fuse(rows).removeSplitter()
    if not plate.isValid() or len(plate.Solids) != 1:
        raise ValueError('Gauge rows must form one valid solid')
    return plate


def archive(output, mesh):
    with ZipFile(B25 / 'R5-B25-P2S.3mf') as base:
        model = etree.fromstring(base.read(MODEL))
        config = etree.fromstring(base.read(MODEL_SETTINGS))
        relations = etree.fromstring(base.read(MODEL_RELS))
        content = etree.fromstring(base.read('[Content_Types].xml'))
        package = etree.fromstring(base.read('_rels/.rels'))
        resource = model.find(f'.//{CORE}object[@id="2"]')
        body = resource.find('.//' + CORE + 'component')
        target = body.get(PRODUCTION+'path')
        item = model.find(f'.//{CORE}item[@objectid="2"]')
        obj = config.find('object[@id="2"]')
        plate = config.find('plate')
        for parent, child in ((resource.getparent(), resource), (item.getparent(), item)):
            for sibling in list(parent):
                if sibling is not child:
                    parent.remove(sibling)
        for child in list(config):
            if child is not obj and child is not plate:
                config.remove(child)
        for relationship in list(relations):
            if relationship.get('Target') != target:
                relations.remove(relationship)
        for relationship in list(package):
            if relationship.get('Target') != '/' + MODEL:
                package.remove(relationship)
        for metadata in obj.findall('metadata'):
            if metadata.get('key') not in ('extruder', 'name') and 'face_count' not in metadata.attrib:
                obj.remove(metadata)
        for key, value in (('enable_support', '0'), ('wall_loops', '4')):
            etree.SubElement(obj, 'metadata', key=key, value=value)
        part = obj.find('part')
        for node in (obj, part):
            node.find("metadata[@key='name']").set('value', 'R5 B25 fit gauge')
        part.find("metadata[@key='source_file']").set('value', 'R5-B25-Fit-Gauge.stl')
        transform = '1 0 0 0 1 0 0 0 1 128 128 27'
        item.set('transform', transform)
        part.find("metadata[@key='matrix']").set('value', '1 0 0 128 0 1 0 128 0 0 1 27 0 0 0 1')
        plate.find("metadata[@key='plater_name']").set('value', 'B25 fit gauge')
        obj.find('metadata[@face_count]').set('face_count', str(len(mesh.faces)))
        part.find('mesh_stat').set('face_count', str(len(mesh.faces)))
        native = target.lstrip('/')
        payloads = {
            MODEL: serialize(model),
            MODEL_SETTINGS: serialize(config),
            MODEL_RELS: serialize(relations),
            '_rels/.rels': serialize(package),
            '[Content_Types].xml': serialize(content),
            SETTINGS: base.read(SETTINGS),
            native: replace_mesh(base.read(native), mesh),
        }
        with ZipFile(output, 'w') as result:
            for name, data in payloads.items():
                result.writestr(ZipInfo(name), data, compress_type=ZIP_DEFLATED)



def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    with TemporaryDirectory() as scratch:
        stl = Path(scratch) / 'R5-B25-Fit-Gauge.stl'
        shape = gauge_shape()
        print_mesh(shape, stl)
        mesh = trimesh.load_mesh(stl)
        archive(args.output, mesh)
    print(json.dumps({'dimensions_mm': list(mesh.extents), 'facets': len(mesh.faces),
                      'volume_mm3': shape.Volume}, indent=2))


if __name__ == '__main__':
    main()
