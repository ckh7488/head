"""Make the editable B16 cable-routing assembly from the released B15 solid model."""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import sys

import FreeCAD as App
from FreeCAD import Vector
import Part

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE/'physics'))
from export_cad import extract
from clearance_routes import FUSE_LENGTH, fuse_passage, wiring_blocks
from jaw_routing import JAW_PORT
from wiring_motion import (
    CAMERA_BORE_RADIUS, CAMERA_BORE_Y, J6_CUT_LENGTH, NECK_CUT_LENGTHS, POWER_LEADS,
    matrices, s_turn,
)
from wiring_check import bundle, jaw_routing

TERMINALS = {
    'J1+': ('5 V WAGO', 'J1 pad 2 /5V_IN'),
    'J1-': ('GND WAGO', 'J1 pad 1 /GND'),
    'J6-branch': ('J6 pin 3 /DXL_BUS', 'DATA WAGO entry X31'),
    'motor3-data': ('DATA WAGO entry X41', 'ID3 DATA'),
    'motor6-data': ('DATA WAGO entry X36', 'ID6 DATA'),
    'fuse-in': ('5 V WAGO', 'ID6 fuse input'),
}


def cable_passage(y0, y1, top):
    """Open-bottom notch with a self-supporting roof across the two power leads."""
    outline = [(-12.5,-85.),(-2.5,-85.),(-2.5,top-1.5),(-4.,top),
               (-11.,top),(-12.5,top-1.5)]
    profile = Part.makePolygon([Vector(x,y0,z) for x,z in outline+outline[:1]])
    return Part.Face(profile).extrude(Vector(0,y1-y0,0))


def pipe(points, radius):
    coords = [Vector(*p) for p in points]
    line = Part.BSplineCurve()
    line.interpolate(coords)
    wire = Part.Wire([line.toShape()])
    section = Part.Wire([Part.makeCircle(radius,coords[0],line.tangent(line.FirstParameter)[0])])
    shell = wire.makePipeShell([section],True,False)
    if shell.isNull() or not shell.isValid() or len(shell.Solids) != 1:
        raise ValueError('The cable sweep did not form a closed solid')
    return shell


def reliefs(doc):
    ground, _, _ = s_turn(POWER_LEADS['J1-'].splice, POWER_LEADS['J1-'].fixed_guide)
    port = Part.makeCylinder(CAMERA_BORE_RADIUS,38.,Vector(0,CAMERA_BORE_Y,-59.))
    lead_in = Part.makeCone(CAMERA_BORE_RADIUS, CAMERA_BORE_RADIUS+.42,.42,
                           Vector(0,CAMERA_BORE_Y,-33.32))
    lead_out = Part.makeCone(CAMERA_BORE_RADIUS+.42, CAMERA_BORE_RADIUS,.42,
                            Vector(0,CAMERA_BORE_Y,-37.9))
    plug_width,plug_depth=8.4,5.8
    plug = Part.makeBox(plug_width,plug_depth,38.,Vector(-plug_width/2,CAMERA_BORE_Y-plug_depth/2,-59.))
    plug = plug.makeFillet(.42,[edge for edge in plug.Edges if edge.BoundBox.ZLength > 30.])
    jaw_port = Part.makeCylinder(1.65,31.,Vector(*JAW_PORT,-56.))
    jaw_entry = Part.makeCone(2.05,1.65,.65,Vector(*JAW_PORT,-38.))
    jaw_exit = Part.makeCone(1.65,2.05,.65,Vector(*JAW_PORT,-33.45))
    cuts = {
        'Part000': [cable_passage(85.,97.,-65.75), pipe(ground,2.05), pipe(fuse_passage(),1.6)],
        'CableSaddle': [cable_passage(89.8,104.,-66.95)],
        'Part007': [port, lead_in, lead_out, plug, jaw_port, jaw_entry, jaw_exit],
    }
    for name, tools in cuts.items():
        obj = doc.getObject(name)
        updated = obj.Shape.cut(tools).removeSplitter()
        if not updated.isValid() or len(updated.Solids) != 1:
            raise ValueError(f'{obj.Label} no longer has a single printable solid')
        reduction = obj.Shape.Volume-updated.Volume
        if reduction <= 0.01:
            raise ValueError(f'{obj.Label} has no room-making cut')
        obj.Shape = updated
        print(f'{name}: {reduction:.2f} mm³ removed',flush=True)


def add_paths(doc, layout, wiring, cut_lengths):
    group = doc.addObject('App::DocumentObjectGroup','WiringRouting')
    group.Label = 'B16 fixed-length wiring · hatch closed, neck neutral'
    for block in wiring_blocks(wiring):
        if block['id'] not in ('Wdata','ID1EH','ID6EH'):
            continue
        envelope = doc.addObject('Part::Feature','Harness'+block['id'])
        envelope.Label = block['label']+' · envelope'
        envelope.Shape = Part.makeBox(*block['size'],Vector(*(x-s/2 for x,s in zip(block['center'],block['size']))))
        if envelope.ViewObject:
            envelope.ViewObject.ShapeColor = (.32,.66,.49)
            envelope.ViewObject.Transparency = 65
        group.addObject(envelope)
    transforms = matrices(layout)
    cables = bundle(wiring,cut_lengths,transforms,0.,packed=True)
    for cable in jaw_routing(cables,(),transforms):
        name, diameter, length, points = cable.name,cable.diameter,cable.length,cable.points
        obj = doc.addObject('Part::Feature','HarnessWire')
        obj.Label = f'{name}  ·  {length:.1f} mm'
        obj.addProperty('App::PropertyLength','CableLength','Routing')
        obj.addProperty('App::PropertyLength','JacketDiameter','Routing')
        obj.addProperty('App::PropertyLength','MinimumBend','Routing')
        obj.CableLength = length
        obj.JacketDiameter = diameter
        obj.MinimumBend = cable.radius
        obj.setEditorMode('CableLength',1)
        obj.setEditorMode('MinimumBend',1)
        if name in TERMINALS:
            obj.addProperty('App::PropertyString','FromTerminal','Routing')
            obj.addProperty('App::PropertyString','ToTerminal','Routing')
            obj.FromTerminal,obj.ToTerminal=TERMINALS[name]
            obj.setEditorMode('FromTerminal',1)
            obj.setEditorMode('ToTerminal',1)
        obj.Shape = Part.makePolygon([Vector(*p) for p in points])
        if obj.ViewObject:
            obj.ViewObject.LineWidth = 4. if name=='USB-Camera' or name in POWER_LEADS else 2.
            obj.ViewObject.LineColor = ((0.10,0.69,0.85) if name=='USB-Camera' else
                                        (0.80,0.26,0.17) if name.endswith('+') or name.endswith('-power') else
                                        (0.68,0.54,0.21))
        group.addObject(obj)
    doc.recompute()


def make(source, cad, wiring, world):
    data = json.loads(wiring.read_text(encoding='utf-8'))
    if data['cad_sha256'] != sha256(source.read_bytes()).hexdigest():
        raise ValueError('Base CAD and wiring have different revisions')
    doc = App.openDocument(str(source.resolve()))
    try:
        reliefs(doc)
        doc.R5.Label = 'R5 B16 · cable routing review'
        doc.Label = 'R5 B16 cable routing'
        doc.recompute()
        # Export the collision geometry before adding the separately checked cables.
        doc.saveAs(str(cad.resolve()))
    finally:
        App.closeDocument(doc.Name)
    extract(cad.resolve(), world.resolve(), True)

    layout = json.loads((world/'cad_parts.json').read_text(encoding='utf-8'))
    cut_lengths = {**NECK_CUT_LENGTHS,'J6-branch':J6_CUT_LENGTH,'fuse-in':FUSE_LENGTH}
    (world/'cut-lengths.json').write_text(json.dumps(cut_lengths,indent=2)+'\n',encoding='utf-8')
    (world/'wiring-blocks.json').write_text(json.dumps(wiring_blocks(data),ensure_ascii=False)+'\n',encoding='utf-8')
    doc = App.openDocument(str(cad.resolve()))
    try:
        add_paths(doc, layout, data, cut_lengths)
        doc.save()
    finally:
        App.closeDocument(doc.Name)
    layout['source_sha256'] = sha256(cad.read_bytes()).hexdigest()
    (world/'cad_parts.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    p = ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=HERE/'R5-B15-Assembly.FCStd')
    p.add_argument('--wiring',type=Path,default=ROOT/'web/assets/wiring.json')
    p.add_argument('--cad',type=Path,required=True)
    p.add_argument('--world',type=Path,required=True)
    args = p.parse_args()
    args.cad.parent.mkdir(parents=True,exist_ok=True)
    make(**vars(args))
