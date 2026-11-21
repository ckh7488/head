"""Give the B25 right opening stop clearance for 62 commanded ticks."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree
from zipfile import ZipFile

import FreeCAD as App
import manifold3d as md

from build_b21_print import build as pack_prints
from build_b25_bearing_fit import JAW as STAY_FILE, archived_mesh
from build_b25_jaw_retention import replace_mesh
from build_b25_jaw_side_clearance import STAY, STAY_ROTATION, print_cutter, trimmed
from check_b25_jaw_retention import geometry


def stop_relief():
    x_min, x_max = 45.9, 54.
    z_min, z_max = 69., 82.
    width = 12.
    end_wall_y_at_bottom = -10.825
    return md.Manifold.cube((x_max-x_min, width, z_max-z_min)).transform((
        (1., 0., 0., x_min),
        (0., 1., .06, end_wall_y_at_bottom-width),
        (0., 0., 1., z_min),
    ))


def apply(doc, project):
    world_cutter = stop_relief()
    obj = doc.getObject(STAY)
    stock = geometry(obj)
    changed, volume_removed = trimmed(stock, world_cutter, STAY)
    with ZipFile(project) as archive:
        archived, _ = archived_mesh(archive, STAY_FILE, 9)
    cutter = print_cutter([stock], archived, STAY_ROTATION, world_cutter)
    print_body, print_removed = trimmed(archived, cutter, STAY_FILE)
    if abs(volume_removed-print_removed) > .005:
        raise ValueError('Native and in-print stop relief differ')
    replace_mesh(obj, changed)
    return {STAY_FILE: (STAY_FILE, print_body)}, {
        'modified_part': STAY,
        'plate': 9,
        'native_removed_mm3': volume_removed,
        'print_removed_mm3': print_removed,
        'cutter_world_axes_mm': {'x': [45.9, 54.], 'z': [69., 82.], 'y_at_z69': -10.825,
                                  'y_increase_per_z': .06}
    }


def digest(path):
    with path.open('rb') as file:
        return file_digest(file,'sha256').hexdigest()


def native_resource(archive):
    xml = ElementTree.fromstring(archive.read('Document.xml'))
    props = xml.find(f"./ObjectData/Object[@name='{STAY}']/Properties")
    mesh_file = props.find("./Property[@name='Mesh']/Mesh").attrib['file']
    location = props.find("./Property[@name='Placement']/PropertyPlacement").attrib
    return mesh_file, location


def save_native_mesh_only(source, serialized, output):
    """Preserve unrelated FreeCAD objects' original shape streams and metadata."""
    with ZipFile(source) as stock, ZipFile(serialized) as temporary, ZipFile(output, 'w') as result:
        old_mesh, old_placement = native_resource(stock)
        new_mesh, new_placement = native_resource(temporary)
        if old_placement != new_placement:
            raise ValueError('The stop part placement changed')
        for info in stock.infolist():
            data = temporary.read(new_mesh) if info.filename == old_mesh else stock.read(info)
            result.writestr(info, data)


def build(source, project, output):
    output = output.resolve()
    if output in (source.resolve().parent, project.resolve().parent):
        raise ValueError('Choose a separate output directory')
    output.mkdir(parents=True, exist_ok=True)
    doc = App.openDocument(str(source.resolve()))
    try:
        replacements, details = apply(doc, project)
        doc.recompute()
        with TemporaryDirectory(dir=output) as temporary:
            serialized = Path(temporary) / source.name
            doc.saveAs(str(serialized))
            save_native_mesh_only(source, serialized, output / source.name)
    finally:
        App.closeDocument(doc.Name)
    pack_prints(output / project.name, replacements, output / 'print-build.json',
                source=project, revision='B25', indexed_parts=replacements)
    details['source_cad_sha256'] = digest(source)
    details['cad_sha256'] = digest(output / source.name)
    details['source_project_sha256'] = digest(project)
    details['project_sha256'] = digest(output / project.name)
    details['part_file'] = STAY_FILE
    print(json.dumps(details,indent=2),flush=True)
    (output / 'jaw-62-stop-design.json').write_text(json.dumps(details,indent=2)+'\n')


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    for arg in ('source','project','output'):
        parser.add_argument(arg,type=Path)
    build(**vars(parser.parse_args()))
