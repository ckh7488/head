"""Clear the insertion routes through the open back of the skull."""

from pathlib import Path
from tempfile import TemporaryDirectory

import manifold3d as md
import numpy as np
import trimesh as tr

from primitives import box
from FreeCAD import Vector
import Mesh
import MeshPart

FRONT_TRAVEL = 84.
ORBIT_TRAVEL = 84.
CAMERA_TRAVEL = (0., 66., 45.)
JAW_TRAVEL = 76.


def enclosure_motion(body, travel, clearance=.28):
    bounds = np.asarray(body.bounding_box()).reshape(2, 3)
    lo, hi = bounds
    intervals = np.linspace(lo[2]-.01, hi[2]+.01, max(2, int(np.ceil((hi[2]-lo[2])/1.8))+1))
    shifted = np.array((0., travel, 0.))
    allowance = np.array([(-1., -1., -1.), (1., -1., -1.), (-1., 1., -1.), (1., 1., -1.),
                          (-1., -1., 1.), (1., -1., 1.), (-1., 1., 1.), (1., 1., 1.)]) * clearance
    cuts = []
    for bottom, top in zip(intervals, intervals[1:]):
        layer = md.Manifold.cube((hi[0]-lo[0]+.1, hi[1]-lo[1]+.1, top-bottom))
        layer = layer.translate((lo[0]-.05, lo[1]-.05, bottom))
        for piece in (body ^ layer).decompose():
            vertices = piece.to_mesh().vert_properties[:, :3]
            points = np.vstack([vertices, vertices + shifted])
            expanded = (points[:, None, :] + allowance[None, :, :]).reshape(-1, 3)
            cuts.append(md.Manifold.hull_points(expanded))
    return md.Manifold.batch_boolean(cuts, md.OpType.Add)


def front_loading_clearance(doc):
    with TemporaryDirectory() as work:
        path = Path(work) / 'surface.stl'

        def solid(obj=None, shape=None):
            if shape is None and obj.TypeId == 'Mesh::Feature':
                mesh = obj.Mesh.copy()
                transform = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
                mesh.transform(transform.toMatrix())
            else:
                if shape is None:
                    shape = obj.Shape.copy()
                    shape.Placement = obj.getGlobalPlacement()
                mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=.055,
                                             AngularDeflection=.12, Relative=False)
            mesh.write(str(path))
            source = tr.load_mesh(path)
            result = md.Manifold(md.Mesh(np.asarray(source.vertices, dtype=np.float32),
                                         np.asarray(source.faces, dtype=np.uint32)))
            if result.is_empty():
                raise ValueError(f'Cannot make a solid envelope for {getattr(obj, "Name", "clipped yoke")}')
            return result

        shell = doc.Part073
        base = solid(shell)
        tools = [enclosure_motion(solid(doc.getObject(name)), FRONT_TRAVEL)
                 for name in ('Part012', 'Part013', 'Part014', 'Part015',
                              'Part025', 'Part026', 'Part027', 'Part028')]
        for low, high in ((-60., -48.), (48., 60.)):
            wing = doc.Part011.Shape.common(box(low, high, -20., 32., 97., 125.))
            tools.append(enclosure_motion(solid(shape=wing), FRONT_TRAVEL))
        for name in ('Part076', 'Part077'):
            tools.append(enclosure_motion(solid(doc.getObject(name)), ORBIT_TRAVEL, .22))
        for lo, hi in ((-53.78, -51.68), (51.68, 53.78)):
            tools.append(solid(shape=box(lo, hi, -26.76, -23.84, 126.42, 128.58)))
        for name in ('Jaw_36_left_jaw_servo_stay', 'Jaw_37_right_jaw_bearing_stay'):
            upright = solid(doc.getObject(name)).rotate((90., 0., 0.))
            tools.append(enclosure_motion(upright, JAW_TRAVEL).rotate((-90., 0., 0.)))

        relieved = base - md.Manifold.batch_boolean(tools, md.OpType.Add)
        pieces = relieved.decompose()
        primary = max(pieces, key=lambda piece: piece.volume())
        if primary.volume() < .98 * base.volume() or relieved.volume()-primary.volume() > 45.:
            detached = sorted((round(p.volume(), 2), p.bounding_box()) for p in pieces if p is not primary)
            raise ValueError(f'Front shell relief: {base.volume():.1f} -> {primary.volume():.1f} mm³, '
                             f'detached {detached[-6:]}')
        model = primary.to_mesh()
        mesh = tr.Trimesh(vertices=model.vert_properties[:, :3], faces=model.tri_verts, process=False)
        parent = shell.getGlobalPlacement().multiply(shell.Placement.inverse())
        mesh.apply_transform(np.array(parent.inverse().toMatrix().A).reshape(4, 4))
        mesh.export(path)
        shell.Mesh = Mesh.Mesh(str(path))


def finish_camera(bracket):
    relief = [box(x0, x1, -52., -46.5, 70.55, 74.05)
              for x0, x1 in [(-19.25, -16.8), (16.8, 19.25)]]
    return bracket.cut(relief).removeSplitter()
