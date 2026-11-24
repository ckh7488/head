"""Route the fixed Eaton tail to the retained U20CAM USB-A pigtail."""
from argparse import ArgumentParser
from math import cos, radians, sin
from pathlib import Path
import json

import FreeCAD as App
import Part
import numpy as np

from build_b19_review_fixes import replace
from export_cad import world_shape
from primitives import cylinder

V=App.Vector
START=np.array([58.,103.,-28.91788776547])
ARC_START_Y=99.6
PLUG_Y=158.
R=25.
N=np.array((cos(radians(56.)),0.,-sin(radians(56.))))
D=np.array((0.,-1.,0.))


def fixed_tail_points():
    begin=START.copy()
    begin[1]=ARC_START_Y
    def arc(ang):
        return begin+R*(sin(ang)*D+(1.-cos(ang))*N)
    finish=arc(np.pi)
    plug=finish.copy()
    plug[1]=PLUG_Y
    return begin,arc(np.pi/2),finish,plug


def sweep(edges, radius, direction):
    way=Part.Wire(edges)
    profile=Part.Wire([Part.makeCircle(radius, edges[0].Vertexes[0].Point, V(*direction))])
    path=way.makePipeShell([profile],True,False)
    if not path.isValid() or len(path.Solids)!=1:
        raise ValueError('Expected one valid fixed pigtail solid')
    return path


def apply(doc):
    start,mid,end,plug=fixed_tail_points()
    pieces=[Part.makeLine(V(*START),V(*start)),Part.Arc(V(*start),V(*mid),V(*end)).toShape(),
            Part.makeLine(V(*end),V(*plug))]
    nominal=sweep(pieces,2.,(0.,-1.,0.))
    clamp=sweep(pieces,2.1,(0.,-1.,0.))
    plug_actor=doc.getObject('CameraUSB')
    old_plug=world_shape(plug_actor)
    box_=old_plug.BoundBox
    offset=np.array([box_.Center.x,box_.YMin,box_.Center.z])
    conn=old_plug.translated(V(*(plug-offset)))
    start_splice=140.
    end_splice=153.
    splice=cylinder(3.5,end_splice-start_splice,(plug[0],start_splice,plug[2]),(0.,1.,0.))
    skip=('Harness','RearLead3','HubRearClearance','Ballast')
    result={}
    for label,shape in [('tail_OD4.0',nominal),('tail_OD4.2',clamp),('splice_OD7x13',splice),('USB_A_body',conn)]:
        guard=shape.BoundBox
        checks={}
        for actor in doc.Objects:
            if actor.TypeId!='Part::Feature' or actor.Name=='CameraUSB' or actor.Name.startswith(skip):
                continue
            solid=world_shape(actor)
            if solid.isNull() or not guard.intersect(solid.BoundBox):
                continue
            overlap=shape.common(solid).Volume
            if overlap>1.e-6:
                checks[actor.Name]=overlap
        result[label]=checks
    if any(result.values()):
        raise ValueError(f'Fixed camera tail clashes with nominal stationary hardware: {result}')
    replace(plug_actor,conn)
    plug_actor.Label='Camera OEM USB-A pigtail · retained plug housing envelope'
    if doc.getObject('RearLead3_1'):
        replace(doc.RearLead3_1,nominal)
        doc.RearLead3_1.Label='Camera fixed tail · R25 with stationary sleeve'
    splice_actor=doc.addObject('Part::Feature','EatonRearStationarySplice')
    splice_actor.Label='Camera stationary splice gauge · Ø7 × 13 mm'
    splice_actor.Shape=splice
    doc.RearConnections.addObject(splice_actor)
    return {'rear_fixed_tail_radius_mm':R,'rear_fixed_tail_mm':Part.Wire(pieces).Length,
            'first_anchor_mm':START.tolist(),'usb_a_seat_mm':plug.tolist(),
            'splice_straight_y_mm':[start_splice,end_splice],'minimum_reserve_x_mm':plug[0],
            'stock_cad_overlaps':result,
            'plug_proxy':'Existing OEM-sized USB-A proxy in native CAD. Verify molded shoulders and outlet pull on received unit.'}


if __name__=='__main__':
    p=ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    doc=App.openDocument(str(a.source.resolve()))
    r=apply(doc)
    doc.recompute();doc.saveAs(str(a.output.resolve()))
    App.closeDocument(doc.Name)
    a.output.with_suffix('.json').write_text(json.dumps(r,indent=2)+'\n')
