"""B25 fixed support for the Eaton rolling R19 reserve loop."""
from argparse import ArgumentParser
from pathlib import Path
import json

import FreeCAD as App
import MeshPart
import Part

from build_b19_review_fixes import replace
from export_cad import world_shape
from primitives import box

TOP=(58.,103.,-28.91788776547)


def rear_guide():
    x,y,z=TOP
    tunnel=box(53.6,62.5,100.3,105.6,-33.,-24.9)
    opening=Part.makeCylinder(2.20,8.,App.Vector(x,99.5,z),App.Vector(0,1,0))
    profile=((51.85,-71.5),(54.2,-71.5),(52.9,-55.5),(51.85,-55.5))
    outline=Part.makePolygon([App.Vector(a,108.,b) for a,b in (*profile,profile[0])])
    rib=Part.Face(outline).extrude(App.Vector(0,13,0))
    base=box(51.8,64.3,103.,182.2,-74.,-70.9)
    sides=[
        box(51.8,54.,103.,182.2,-71.1,-24.),
        box(62.2,64.3,103.,182.2,-71.1,-24.),
        box(53.8,62.4,180.,182.2,-71.1,-24.),
    ]
    weld=[
        box(49.4,53.4,108.,121.,-73.,-67.8),
        box(49.4,53.4,121.,126.,-73.,-69.),
        rib,box(54.,62.5,167.,177.,-83.,-73.9),tunnel.cut(opening),
    ]
    shape=base.fuse(sides+weld).removeSplitter()
    # Open strap paths at the fixed length mark. The tube ends still guide the
    # bare donor through the support before either sleeve is installed.
    top=box(54.4,61.6,101.7,104.3,-29.10,-24.1)
    left=box(53.9,55.5,101.7,104.3,-32.5,-24.1)
    right=box(60.5,62.1,101.7,104.3,-32.5,-24.1)
    return shape.cut([top,left,right,box(54.4,61.6,101.7,104.3,-32.4,-31.47)]).removeSplitter()


def apply(doc, printed_delta=None):
    guide=rear_guide()
    stock=world_shape(doc.CableSaddle)
    overlap=guide.common(stock).Volume
    shape=stock.fuse(guide).removeSplitter()
    if not shape.isValid() or len(shape.Solids)!=1 or overlap<=0.:
        raise ValueError('The Eaton guide and original cable support must be one manufacturable solid.')
    no_region=('Harness','RearLead3','HubRearClearance','Ballast')
    no_actor={'CableSaddle','CameraUSB'}
    rigid_hits={}
    bounds=guide.BoundBox
    for other in doc.Objects:
        if other.TypeId!='Part::Feature' or other.Name in no_actor or other.Name.startswith(no_region):
            continue
        s=world_shape(other)
        if s.isNull() or not bounds.intersect(s.BoundBox):
            continue
        v=guide.common(s).Volume
        if v>1e-6:
            rigid_hits[other.Name]=v
    gate=world_shape(doc.CableGate)
    clearance=guide.distToShape(gate)[0]
    if rigid_hits:
        raise ValueError(f'New Eaton guide overlaps rigid stock: {rigid_hits}')
    replace(doc.CableSaddle,shape)
    if printed_delta is not None:
        mesh=MeshPart.meshFromShape(Shape=guide,LinearDeflection=.04,AngularDeflection=.11,Relative=False)
        mesh.write(str(printed_delta))
    return {'rear_u_guard_contiguous_joint_mm3':overlap,'rear_u_guard_added_volume_mm3':shape.Volume-stock.Volume,
            'nominal_gate_clearance_mm':clearance,'inadmissible_stock_volume_overlaps':rigid_hits,'top_anchor_mm':TOP,
            'fixed_guard_inner_y_limit_mm':180.,'rear_tie_slot_y_range_mm':[101.7,104.3],'guide_inner_x_range_mm':[54.,62.2]}


if __name__=='__main__':
    p=ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    d=App.openDocument(str(a.source.resolve()))
    proof=apply(d,a.output.with_suffix('.stl'))
    d.recompute()
    d.saveAs(str(a.output.resolve()))
    App.closeDocument(d.Name)
    a.output.with_suffix('.json').write_text(json.dumps(proof,indent=2)+'\n')
