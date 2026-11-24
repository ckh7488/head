"""Apply a deeper yoke-facing relief on the existing right cheek stay."""
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import json

import FreeCAD as App
import Mesh
import manifold3d as md
import numpy as np
import trimesh

from build_b21_print import build as pack_prints
from build_b22_fused_skull import solid
from build_b25_bearing_fit import JAW as PRINT_PART, JAW_CENTER, section
from build_b25_jaw_retention import mesh_from_solid, replace_mesh
from build_b25_large_bearing_variants import source_mesh
from check_b25_jaw_retention import geometry


PART='Jaw_37_right_jaw_bearing_stay'
FACE_Y=-10.169999885559082
X_MIN,X_MAX=47.6,57.2
Z_MIN,Z_MAX=98.25,109.5
WORLD_TO_PRINT=np.array(((0.,0.,-1.,90.75),(0.,1.,0.,14.499639630317688),(1.,0.,0.,-53.700143814086914)))


def relief(extra):
    return md.Manifold.cube((X_MAX-X_MIN,extra+.02,Z_MAX-Z_MIN)).translate((X_MIN,FACE_Y-extra,Z_MIN))


def cut(stock, tool):
    body=solid(stock)
    changed=body-tool
    result=mesh_from_solid(changed)
    if not (result.is_volume and result.body_count==1 and result.nondegenerate_faces().all()
            and np.allclose(stock.bounds,result.bounds,atol=1e-6,rtol=0)):
        raise ValueError('The right stay must remain a single printable part with its original envelope')
    return result,float(body.volume()-changed.volume())


def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('cad',type=Path)
    parser.add_argument('project',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--depth',type=float,default=.70)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    out_cad=args.output/'R5-B25-Assembly.FCStd'
    out_project=args.output/'R5-B25-P2S.3mf'
    if out_cad.resolve()==args.cad.resolve() or out_project.resolve()==args.project.resolve():
        raise ValueError('Write the candidate to a separate folder')
    tool=relief(args.depth)
    doc=App.openDocument(str(args.cad.resolve()))
    try:
        part=doc.getObject(PART)
        native,removed=cut(geometry(part),tool)
        replace_mesh(part,native)
        motion=json.loads(doc.R5.MotionGeometry)
        motion['right_cheek_yoke_relief']={'depth_added_mm':args.depth,'world_cut_x_mm':[X_MIN,X_MAX],
                                 'world_cut_z_mm':[Z_MIN,Z_MAX],'new_y_face_mm':FACE_Y-args.depth}
        doc.R5.MotionGeometry=json.dumps(motion,ensure_ascii=False)
        doc.recompute()
        doc.saveAs(str(out_cad.resolve()))
    finally:
        App.closeDocument(doc.Name)
    with ZipFile(args.project) as archive:
        vertices,faces,setup=source_mesh(archive,PRINT_PART)
    printed,print_removed=cut(trimesh.Trimesh(vertices,faces,process=False),tool.transform(WORLD_TO_PRINT))
    bearing={'pocket':section(printed,2,-11.5,JAW_CENTER,10.15),
             'shoulder':section(printed,2,-14.10,JAW_CENTER,7.10)}
    print_path=args.output/PRINT_PART
    printed.copy().apply_translation((0,0,-printed.bounds[0,2])).export(print_path)
    pack_prints(out_project,{PRINT_PART:(PRINT_PART,printed)},args.output/'print-build.json',source=args.project,
                revision='B25',indexed_parts=(PRINT_PART,))
    report={'baseline_sha256':sha256(args.cad.read_bytes()).hexdigest(),'cad_sha256':sha256(out_cad.read_bytes()).hexdigest(),
            'print_sha256':sha256(out_project.read_bytes()).hexdigest(),'cut':motion['right_cheek_yoke_relief'],
            'world_to_print':WORLD_TO_PRINT.tolist(),'removed_mm3':{'cad':removed,'p2s':print_removed},
            'p2s_print_setup':setup,'retained_bearing_sections':bearing}
    (args.output/'yoke-jaw-cut.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':
    main()
