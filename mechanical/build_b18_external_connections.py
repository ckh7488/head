"""Build the B18 split rear cable guide with externally accessible lead ends."""
from argparse import ArgumentParser
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sys

import FreeCAD as App
from FreeCAD import Vector as V
import Part

from fixtures import CABLE_CENTER_Z, CABLE_LANES
from primitives import box, cylinder, print_mesh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE/'physics'))
from export_cad import tessellate, world_shape


GUIDE_START_Y = 104.85
GUIDE_END_Y = 114.4
STRAP_Y = 109.65
STRAP_Y_WIDTH = 3.6
STRAP_HALF_X = .84
STRAP_LOW = -6.75
STRAP_SHOULDER = -5.50
STRAP_PEAK = -3.55
BUCKLE_HEIGHT = 4.10
BUCKLE_CLEARANCE = .20
REAR_Y = 125.
Z = CABLE_CENTER_Z
COVER_TRAVEL = 25.
TIP_TRAVEL = 16.
TRAY_COLOR = (.28, .45, .49)
COVER_COLOR = (.42, .55, .57)
POWER_COLOR = (.94, .66, .23)
USB_COLOR = (.21, .51, .66)


@dataclass(frozen=True)
class Lane:
    name: str
    x: float
    pocket_width: float
    pitch: float
    diameter: float
    guide_diameter: float
    datum_y: float
    lead_end_y: float
    connector_names: tuple[str, ...]
    label: str

    @property
    def cable_centers(self):
        return (self.x-self.pitch/2, self.x+self.pitch/2) if self.pitch else (self.x,)

    @property
    def strap_run(self):
        return self.pitch/2+self.diameter/2+1.15


def lane_specs():
    specs = (
        ('5V XT30', 2.057, 2.80, 97.42, 159., ('InputXT30','SupplyXT30'), '5 V · XT30'),
        ('neck XT60', 3.023, 3.80, 75.32, 171., ('InputXT60Mate','InputXT60'), '목 12 V · XT60'),
        ('camera USB-A', 4.80, 5.50, 75.12, 158., ('CameraUSB',), '카메라 USB'),
        ('OpenRB USB-A', 4.80, 5.50, 75.12, 169., ('ControlUSB',), 'OpenRB USB'),
    )
    result = []
    for part, spec in zip(CABLE_LANES, specs, strict=True):
        name, x, pocket, *_, pitch = part
        label, d, guide, datum, end, models, text = spec
        if name != label:
            raise ValueError(f'Unexpected cable lane: {name}')
        result.append(Lane(name,x,pocket[0],pitch,d,guide,datum,end,models,text))
    return tuple(result)


LANES = lane_specs()


def rounded_guide(x, radius):
    lead = cylinder(radius,GUIDE_END_Y-GUIDE_START_Y+.2,(x,GUIDE_START_Y-.1,Z),(0,1,0))
    start = Part.makeCone(radius+.60,radius,1.05,V(x,GUIDE_START_Y-.05,Z),V(0,1,0))
    finish = Part.makeCone(radius+.60,radius,1.05,V(x,GUIDE_END_Y+.05,Z),V(0,-1,0))
    return lead.fuse([start,finish])


def strap_opening(lane):
    left, right = (lane.x+sign*lane.strap_run for sign in (-1,1))
    y0,y1 = STRAP_Y-STRAP_Y_WIDTH/2,STRAP_Y+STRAP_Y_WIDTH/2
    # Sloped roof keeps supports out of the enclosed lacing tunnel.
    section = [(y0,STRAP_LOW),(y1,STRAP_LOW),(y1,STRAP_SHOULDER),
               (STRAP_Y,STRAP_PEAK),(y0,STRAP_SHOULDER)]
    outline = Part.makePolygon([V(left-STRAP_HALF_X,y,Z+z) for y,z in [*section,section[0]]])
    tunnel = Part.Face(outline).extrude(V(right-left+2*STRAP_HALF_X,0.,0.))
    legs = [box(x-STRAP_HALF_X,x+STRAP_HALF_X,y0,y1,Z+STRAP_LOW,Z+.12) for x in (left,right)]
    return tunnel.fuse(legs)


def split_tray(saddle, cover):
    supports, guides, straps, head_spaces = [], [], [], []
    for lane in LANES:
        w = lane.pocket_width/2+.35
        supports.append(box(lane.x-w,lane.x+w,GUIDE_START_Y,GUIDE_END_Y,Z-8.85,Z))
        guides.extend(rounded_guide(cx,lane.guide_diameter/2) for cx in lane.cable_centers)
        straps.append(strap_opening(lane))
        x = lane.x-lane.strap_run
        ceiling = Z+lane.diameter/2+BUCKLE_CLEARANCE+BUCKLE_HEIGHT+.35
        head_spaces.append(box(x-2.68,x+2.68,STRAP_Y-3.30,STRAP_Y+3.30,Z-.1,ceiling))
        head_spaces.append(box(lane.x-lane.strap_run-.94,lane.x+lane.strap_run+.94,
                               STRAP_Y-1.95,STRAP_Y+1.95,Z-.1,Z+lane.diameter/2+1.5))
    lower = saddle.fuse(supports).cut([*guides,*straps]).removeSplitter()
    upper = cover.cut(head_spaces).removeSplitter()
    for name, solid in (('lacing tray',lower),('removable cover',upper)):
        if solid.isNull() or not solid.isValid() or len(solid.Solids)!=1:
            raise ValueError(f'{name} must be a single valid solid')
    return lower,upper


def lacing_gauge(lane):
    """Rigid envelope of the installed 2.5 x 1 mm strap and its buckle."""
    x,w = lane.x,lane.strap_run
    y0,y1 = STRAP_Y-1.25,STRAP_Y+1.25
    top = Z+lane.diameter/2+.02
    bottom = Z-6.40
    sides = [box(xx-.47,xx+.47,y0,y1,bottom,top+.87) for xx in (x-w,x+w)]
    cross = box(x-w-.47,x+w+.47,y0,y1,bottom,bottom+.94)
    cap = box(x-w-.47,x+w+.47,y0,y1,top,top+.87)
    head_floor = Z+lane.diameter/2+BUCKLE_CLEARANCE
    head = box(x-w-2.32,x-w+2.32,STRAP_Y-2.45,STRAP_Y+2.45,head_floor,head_floor+BUCKLE_HEIGHT)
    return cross.fuse([*sides,cap,head]).removeSplitter()


def tail_shapes(lane):
    return tuple(cylinder(lane.diameter/2,lane.lead_end_y-lane.datum_y,(x,lane.datum_y,Z),(0,1,0))
                 for x in lane.cable_centers)


def plug_housings(lane):
    x, y = lane.x,lane.lead_end_y
    if lane.pitch:
        width,height,body = (10.2,5.6,12.4) if lane.pitch<6 else (15.3,7.9,13.7)
        bounds = x-width/2,x+width/2
        z0,z1=Z-height/2,Z+height/2
        robot=box(*bounds,y,y+body,z0,z1)
        supply=box(*bounds,y+body,y+body+body,z0,z1)
        return robot,supply
    body = box(x-7.85,x+7.85,y,y+37.8,Z-4.15,Z+4.15)
    metal = box(x-6.,x+6.,y+37.8,y+49.6,Z-2.25,Z+2.25)
    return (body.fuse(metal).removeSplitter(),)


def put_shape(obj, shape):
    parent = obj.getParentGeoFeatureGroup()
    if parent:
        shape = shape.copy()
        shape.Placement = parent.getGlobalPlacement().inverse().multiply(shape.Placement)
    obj.Shape = shape


def style(obj, color):
    if obj.ViewObject:
        obj.ViewObject.ShapeColor = color


def new_fixed(doc, group, name, label, shape, color):
    obj = doc.addObject('Part::Feature',name)
    obj.Label = label
    obj.Shape = shape
    obj.addProperty('App::PropertyString','Motion','Wiring')
    obj.Motion = 'fixed'
    group.addObject(obj)
    style(obj,color)
    return obj


def apply_layout(doc):
    lower,cover = split_tray(world_shape(doc.CableSaddle),world_shape(doc.CableGate))
    for obj,shape,label,color in (
        (doc.CableSaddle,lower,'40 Rear cable guide · four lacing points',TRAY_COLOR),
        (doc.CableGate,cover,'42 Removable rear cable cover',COVER_COLOR),
    ):
        put_shape(obj,shape)
        obj.Label=label
        style(obj,color)
    group=doc.addObject('App::DocumentObjectGroup','RearConnections')
    group.Label='B18 rear connections · cable paths and connector envelopes'
    for i,lane in enumerate(LANES,1):
        color=POWER_COLOR if lane.pitch else USB_COLOR
        for name,shape in zip(lane.connector_names,plug_housings(lane),strict=True):
            supply=name in ('SupplyXT30','InputXT60')
            suffix=' · adapter side' if supply else ' · external end on robot lead'
            obj=doc.getObject(name)
            if obj is None:
                new_fixed(doc,group,name,lane.label+suffix,shape,color)
            else:
                put_shape(obj,shape)
                obj.Label=lane.label+suffix
                style(obj,color)
        for j,shape in enumerate(tail_shapes(lane),1):
            color = ((.68,.21,.19) if j==2 else (.20,.23,.28)) if lane.pitch else USB_COLOR
            tail = new_fixed(doc,group,f'RearLead{i}_{j}',lane.label+' · continuous lead from routing datum',shape,color)
            tail.addProperty('App::PropertyLength','DatumToHousing','Wiring')
            tail.DatumToHousing=lane.lead_end_y-lane.datum_y
        new_fixed(doc,group,f'CableTie{i}',lane.label+' · strain relief strap envelope',
                  lacing_gauge(lane),(.17,.22,.25))
    doc.Label='R5 B18 · rear connections'
    doc.R5.Label=doc.Label
    doc.recompute()


def manifest(source, output):
    return {
        'source_sha256':sha256(source.read_bytes()).hexdigest(),
        'cad_sha256':sha256(output.read_bytes()).hexdigest(),
        'rear_plane_y_mm':REAR_Y,
        'cover_travel_mm':COVER_TRAVEL,
        'test_unmate_travel_mm':TIP_TRAVEL,
        'lanes':[
            {'name':l.name,'label':l.label,'x_mm':l.x,'guide_diameter_mm':l.guide_diameter,
             'diameter_mm':l.diameter,'datum_y_mm':l.datum_y,'housing_y_mm':l.lead_end_y,
             'exposed_lead_mm':l.lead_end_y-REAR_Y,'models':list(l.connector_names)}
            for l in LANES
        ],
    }


def build(source,output,assets):
    source,output,assets=source.resolve(),output.resolve(),assets.resolve()
    if source==output:
        raise ValueError('Specify a different output path')
    doc=App.openDocument(str(source))
    try:
        apply_layout(doc)
        output.parent.mkdir(parents=True,exist_ok=True)
        assets.mkdir(parents=True,exist_ok=True)
        doc.saveAs(str(output))
        names=['Part000','CableSaddle','CableGate','HubHolder','HubPCB','Part009']
        for i,lane in enumerate(LANES,1):
            names.extend(lane.connector_names)
            names.extend(f'RearLead{i}_{j}' for j in range(1,len(lane.cable_centers)+1))
            names.append(f'CableTie{i}')
        world=assets/'world'
        world.mkdir(exist_ok=True)
        for name in names:
            tessellate(world_shape(doc.getObject(name))).write(str(world/f'{name}.stl'))
        print_mesh(world_shape(doc.CableSaddle),assets/'40-rear-cable-guide-B18.stl')
        print_mesh(world_shape(doc.CableGate),assets/'42-rear-cable-cover-B18.stl','z-')
        (assets/'rear-connections.json').write_text(
            json.dumps(manifest(source,output),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    finally:
        App.closeDocument(doc.Name)


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--assets',type=Path,required=True)
    build(**vars(parser.parse_args()))
