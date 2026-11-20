"""Check grip space, the split cable exit and wire threading in the B18 CAD."""
from argparse import ArgumentParser
from hashlib import sha256
from itertools import combinations, product
import json
from pathlib import Path
import sys

import FreeCAD as App
from FreeCAD import Vector as V

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from build_b18_external_connections import COVER_TRAVEL, LANES, TIP_TRAVEL, Z
from base_clearance import check_pass
from export_cad import world_shape
from fixtures import SADDLE_MOUNTS
from primitives import box, cylinder


def pose_series(end, step):
    return tuple(i*step for i in range(round(end/step)+1))


def rigid(doc,names):
    return {name:world_shape(doc.getObject(name)) for name in names}


def fit_paths(doc):
    case = rigid(doc,('Part000','CableSaddle','CableGate'))
    plug_names = [name for lane in LANES for name in lane.connector_names]
    plugs = rigid(doc,plug_names)
    tie_names = [f'CableTie{i}' for i in range(1,len(LANES)+1)]
    ties = rigid(doc,tie_names)
    leads = rigid(doc,[f'RearLead{i}_{j}' for i,l in enumerate(LANES,1)
                       for j in range(1,len(l.cable_centers)+1)])
    rows = {}

    rows['fixed_leads_and_ties'] = check_pass(
        (shape,obstacle,f'{name} / {part}')
        for (name,shape),(part,obstacle) in product({**leads,**ties}.items(),case.items())
    )
    rows['buckle_clearance_to_jacket'] = check_pass(
        (tie,lead,f'{tie_name} / {lead_name}')
        for (tie_name,tie),(lead_name,lead) in product(ties.items(),leads.items())
    )
    rows['cover_lift_with_leads'] = check_pass(
        (case['CableGate'].translated(V(0,0,up)),shape,f'cover lifted {up:g} mm / {name}')
        for up,(name,shape) in product(pose_series(COVER_TRAVEL,.5),{**leads,**ties}.items())
    )
    rows['lead_pairs'] = check_pass(
        (a,b,f'{an} / {bn}')
        for (an,a),(bn,b) in combinations(leads.items(),2)
    )
    # Measure passage through the fixed wall before fitting the tray.
    rows['usb_head_threading_through_wall'] = check_pass(
        (box(lane.x+dx-8.5,lane.x+dx+8.5,72.,104.,Z+dz-4.9,Z+dz+4.9),
         case['Part000'],lane.name+' USB head through wall')
        for lane,dx,dz in product(LANES[2:],(-.30,0.,.30),(-.30,0.,.30))
    )
    tool_shapes = [cylinder(1.48,82.,(x,y,z),(0,1,0)) for x,y,z in SADDLE_MOUNTS]
    rows['long_driver_beside_external_leads'] = check_pass(
        (tool,part,f'M3 tray driver / {name}')
        for tool,(name,part) in product(tool_shapes,{**plugs,**ties,**leads}.items())
    )

    def unmate_and_grip():
        for lane in LANES:
            own=set(lane.connector_names)
            targets={**case,**{name:shape for name,shape in plugs.items() if name not in own}}
            if lane.pitch:
                fixed=plugs[lane.connector_names[0]]
                slider=plugs[lane.connector_names[1]]
            else:
                fixed=plugs[lane.connector_names[0]]
                # External USB-A female gauge, aligned with the socket side of the tip.
                cy=fixed.BoundBox.YMax
                slider=box(lane.x-8.5,lane.x+8.5,cy-11.8,cy+25.,Z-4.9,Z+4.9)
            fixed_grip = fingers(fixed,lane.x)
            for index,up in enumerate(pose_series(TIP_TRAVEL,.5)):
                shifted=slider.translated(V(0,up,0))
                for item in (shifted, fingers(shifted,lane.x), fixed_grip):
                    for name,obstacle in targets.items():
                        yield item,obstacle,f'{lane.label} unmated {up:g} mm / {name}'
                if lane.pitch and index:
                    yield shifted,fixed,f'{lane.label} adapter separated {up:g} mm'

    rows['unmate_and_grip_outside'] = check_pass(unmate_and_grip())
    return rows


def fingers(shape,x):
    """Space for a top and bottom grip, projected as an 18 x 10 mm footprint."""
    b=shape.BoundBox
    y=(b.YMin+b.YMax)/2
    return box(x-9.,x+9.,y-5.,y+5.,b.ZMin-12.,b.ZMax+12.)


def verify(cad, output):
    doc=App.openDocument(str(cad.resolve()))
    try:
        result=fit_paths(doc)
        proof={
            'cad_sha256':sha256(cad.read_bytes()).hexdigest(),
            'checks':{name:{'pairs':n,'max_overlap_mm3':mm3} for name,(n,mm3) in result.items()},
            'grip_footprint_mm':[18.,10.],
            'grip_height_above_and_below_mm':12.,
            'unmate_travel_mm':TIP_TRAVEL,
            'wall_usb_gauge_mm':[17.,9.8],
            'wall_gauge_offset_mm':.30,
        }
        output.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(proof,indent=2),flush=True)
    finally:
        App.closeDocument(doc.Name)


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('cad',type=Path)
    parser.add_argument('output',type=Path)
    verify(**vars(parser.parse_args()))
