"""Construct and screen captive heat-set rear-cable cover stations on the A4 B25 guide."""
from argparse import ArgumentParser
from pathlib import Path
from zipfile import ZipFile
from hashlib import sha256
import json

import FreeCAD as App
import Mesh, Part
import numpy as np
import trimesh

from build_b21_print import build as pack_prints
from build_b18_external_connections import COVER_TRAVEL
from build_b19_review_fixes import add_part, replace
from check_b25_j2_disconnect import collision_volumes
from export_cad import world_shape
from primitives import cylinder, print_mesh
from stock import socket_screw

UP=(0.,0.,1.)
DOWN=(0.,0.,-1.)
INSERT_DIAMETER=4.6
INSERT_LENGTH=3.
INSERT_TOP=-63.35
INSERT_OUTER_RADIUS=INSERT_DIAMETER/2
PRINT_PILOT_RADIUS=4.15/2
MIN_WALL=1.55
BOSS_RADIUS=INSERT_OUTER_RADIUS+MIN_WALL
BOSS_LOW=-68.55
HEAT_TOOL_RADIUS=2.5
SHANK_RADIUS_RESERVED=1.65
SCREW_LENGTH=16.
SCREW_MAX_LENGTH=16.45
BOTTOM_LENGTH=10.
BOTTOM_MAX_LENGTH=10.45


def apply(doc, report):
    layout=json.loads(doc.R5.MotionGeometry)
    rear=layout['rear_cable_service_nuts']['bolt_seats_mm']
    source={obj.Name:world_shape(obj) for obj in doc.Objects if obj.TypeId=='Part::Feature'}
    guide=source['CableSaddle']
    additions=[]
    removals=[]
    for x,y,seat in rear:
        additions.append(cylinder(BOSS_RADIUS,INSERT_TOP-BOSS_LOW,(x,y,BOSS_LOW)))
        removals.extend((cylinder(HEAT_TOOL_RADIUS,-57.-INSERT_TOP,(x,y,INSERT_TOP)),
                         cylinder(PRINT_PILOT_RADIUS,INSERT_LENGTH+.20,(x,y,INSERT_TOP+.025),DOWN),
                         cylinder(1.80,SCREW_MAX_LENGTH+.25,(x,y,seat),DOWN)))
    with_columns=guide.fuse(additions).removeSplitter()
    updated=with_columns.cut(removals).removeSplitter()
    if not(updated.isValid() and len(updated.Solids)==1):
        raise ValueError('Rear guide must remain a single valid solid')
    changes=updated.cut(guide).removeSplitter()
    cover=source['CableGate']
    # The A4 upper inlet rail fills part of the pre-existing head recess at the second station.
    x,y,seat=rear[1]
    restored_cover=cover.cut(cylinder(3.20,6.,(x,y,seat))).removeSplitter()
    if not(restored_cover.isValid() and len(restored_cover.Solids)==1):
        raise ValueError('Rear cover must remain a single solid after restoring the head recess')
    report['cover_head_recess_removed_mm3']=cover.Volume-restored_cover.Volume
    changed=source.copy()
    changed.update(CableSaddle=updated,CableGate=restored_cover)
    static={k:v for k,v in changed.items() if k!='CableGate'}
    base_static={k:v for k,v in static.items() if k!='CableSaddle'}
    print('Single guide validity, local intersections, screw and keeper checks...',flush=True)
    report['delta_intersections']=collision_volumes(changes,base_static)
    report['volume_added_mm3']=changes.Volume
    report['volume_removed_mm3']=guide.cut(updated).Volume
    # The retained circumferential annulus is at least 1.55 mm thick around the insert's
    # catalog XY outline. It intentionally excludes the original guide-mount bores below it.
    rows=[]
    for x,y,seat in rear:
        zone= cylinder(BOSS_RADIUS,INSERT_LENGTH,(x,y,INSERT_TOP),DOWN).cut(cylinder(INSERT_OUTER_RADIUS,INSERT_LENGTH,(x,y,INSERT_TOP),DOWN))
        xz=cylinder(SHANK_RADIUS_RESERVED,SCREW_MAX_LENGTH,(x,y,seat),DOWN)
        heat=cylinder(HEAT_TOOL_RADIUS-.10,28.,(x,y,INSERT_TOP+.03))
        usable_thread=seat-(SCREW_LENGTH-.35-1.0)+.20
        inserts_hits=collision_volumes(cylinder(INSERT_OUTER_RADIUS,INSERT_LENGTH,(x,y,INSERT_TOP),DOWN),base_static)
        before_nom=cylinder(1.50,SCREW_LENGTH,(x,y,seat),DOWN)
        head_sweep=cylinder(2.78+.10,22.,(x,y,seat+.0001))
        key_shaft=cylinder(2.5/np.sqrt(3)+.15,72.,(x,y,seat+1.35))
        # ISO 4762 head seat must remain flat and 0.20 mm minimum radial support beyond bore.
        bearing=cylinder(2.535,.10,(x,y,seat-.105)).cut(cylinder(1.88,.10,(x,y,seat-.105)))
        out={'xyz':(x,y,seat),'baseline_screw_overlap_nominal_mm3':collision_volumes(before_nom,source),
             'baseline_head_overlap_mm3':collision_volumes(head_sweep,source),
             'updated_head_overlap_mm3':collision_volumes(head_sweep,changed),
             'updated_L_key_shaft_overlap_mm3':collision_volumes(key_shaft,changed),
             'head_seat_annulus_missing_mm3':bearing.cut(restored_cover).Volume,
             'annulus_missing_mm3':zone.cut(updated).Volume,
             'full_thread_margin_beyond_insert_mm':INSERT_TOP-INSERT_LENGTH-usable_thread,
             'screw_worst_shank_collisions_mm3':collision_volumes(xz,changed),
             'insert_against_other_parts_mm3':inserts_hits,
             'heat_tool_worst_collisions_mm3':collision_volumes(heat,static)}
        rows.append(out)
        print(out,flush=True)
    report['rear_stations']=rows
    report['cover_lift_contacts']={}
    cover=restored_cover
    for lift in np.linspace(0,COVER_TRAVEL,51):
        moved=cover.translated(App.Vector(0,0,float(lift)))
        delta=changes.common(moved).Volume if changes.BoundBox.intersect(moved.BoundBox) else 0.
        if delta>1e-7:
            report['cover_lift_contacts'][str(lift)]=delta
    hardware=json.loads(Path('mechanical/revisions/b24/hardware.json').read_text())['hardware']
    report['bottom_stations']=[]
    for row in hardware:
        if not row['id'].startswith('hatchBolt'):
            continue
        x,y,seat=row['seat']
        gauge=cylinder(SHANK_RADIUS_RESERVED,BOTTOM_MAX_LENGTH,(x,y,seat),UP)
        tip=cylinder(SHANK_RADIUS_RESERVED,.45,(x,y,seat+BOTTOM_LENGTH),UP)
        report['bottom_stations'].append({'name':row['id'],'seat':row['seat'],
          'longest_shank_mm':BOTTOM_MAX_LENGTH,'shank_overlap_mm3':collision_volumes(gauge,changed),
          'nearest_stack_at_tip_mm':sorted(((n,tip.distToShape(k)[0]) for n,k in changed.items() if k.BoundBox.intersect(cylinder(8.,16.,(x,y,seat),UP).BoundBox)),key=lambda pair:pair[1])[:3]})
    return updated,restored_cover


def main():
    p=ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--project',type=Path)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    doc=App.openDocument(str(args.source.resolve()))
    try:
        report={'baseline_cad_sha256':sha256(args.source.read_bytes()).hexdigest()}
        result,cover=apply(doc,report)
        move = doc.CableSaddle.getParentGeoFeatureGroup()
        guide_assembled=result.cut([cylinder(INSERT_OUTER_RADIUS,INSERT_LENGTH,(x,y,INSERT_TOP),DOWN)
           for x,y,_ in (row['xyz'] for row in report['rear_stations'])]).removeSplitter()
        if not(guide_assembled.isValid() and len(guide_assembled.Solids)==1):
            raise ValueError('The guide with seated inserts must remain a single solid')
        replace(doc.CableSaddle,guide_assembled)
        replace(doc.CableGate,cover)
        for index,target in enumerate(report['rear_stations'],start=1):
            x,y,z=target['xyz']
            anchor=cylinder(INSERT_OUTER_RADIUS,INSERT_LENGTH,(x,y,INSERT_TOP),DOWN)
            insert=anchor.cut(cylinder(1.5,INSERT_LENGTH,(x,y,INSERT_TOP),DOWN))
            add_part(doc,move,f'RearCableCoverInsert{index}','M3 × 3 rear cable cover insert',insert,'fixed')
        motion=json.loads(doc.R5.MotionGeometry)
        motion['rear_cable_service_nuts'].update({'capture_type':'M3 heat-set inserts','reuses_open_nuts':False,
           'insert_names':[f'RearCableCoverInsert{i}' for i in range(1,6)],'insert_top_mm':INSERT_TOP})
        motion['bottom_board_cover_bolt_length_mm']=BOTTOM_LENGTH
        doc.R5.MotionGeometry=json.dumps(motion,ensure_ascii=False)
        doc.recompute()
        cad=args.output/'R5-B25-Assembly.FCStd'
        doc.saveAs(str(cad.resolve()))
        report['cad_sha256']=sha256(cad.read_bytes()).hexdigest()
        mesh_path=args.output/'40-rear-cable-guide-captive-inserts.stl'
        print_mesh(result,mesh_path)
        cover_path=args.output/'42-rear-cable-cover-service-A4-head-clearance.stl'
        print_mesh(cover,cover_path,'z-')
        if args.project:
            replacements={'40-rear-cable-guide-service.stl':(mesh_path.name,trimesh.load_mesh(mesh_path)),
                          '42-rear-cable-cover-service.stl':(cover_path.name,trimesh.load_mesh(cover_path))}
            pack_prints(args.output/'R5-B25-P2S.3mf',replacements,args.output/'cover-print-build.json',
                        source=args.project,revision='B25',indexed_parts=tuple(replacements))
        (args.output/'cover-service.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2),flush=True)
    finally:
        App.closeDocument(doc.Name)

if __name__=='__main__':
    main()
