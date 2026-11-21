"""Clear the right eye-pitch link during straight insertion of the front shell."""

import json

import FreeCAD as App
import Mesh
import manifold3d as md
import numpy as np
import trimesh

from export_cad import world_mesh


RELIEF_MIN = (60.85, -13.10, 112.40)
RELIEF_MAX = (64.65, -5.05, 117.35)


def front_shell_cut(stock):
    bounds = np.asarray((RELIEF_MIN, RELIEF_MAX))
    shell = md.Manifold(md.Mesh(
        np.ascontiguousarray(stock.vertices, dtype=np.float32),
        np.ascontiguousarray(stock.faces, dtype=np.uint32),
    ))
    tool = md.Manifold.cube(bounds[1]-bounds[0]).translate(bounds[0])
    edited = shell-tool
    native = edited.to_mesh()
    result = trimesh.Trimesh(vertices=native.vert_properties[:, :3], faces=native.tri_verts, process=False)
    removed = shell.volume()-edited.volume()
    if (edited.status() != md.Error.NoError or not result.is_volume or result.body_count != 1
            or not np.allclose(stock.bounds, result.bounds, atol=1e-5, rtol=0.)
            or not 20. < removed < 23.):
        raise ValueError('Front shell relief must preserve the closed shell and its stock envelope')
    return result, removed


def apply(doc):
    obj = doc.Part073
    points, triangles = world_mesh(obj).Topology
    stock = trimesh.Trimesh([tuple(point) for point in points], triangles)
    cut, removed = front_shell_cut(stock)
    mesh = Mesh.Mesh(cut.triangles.tolist())
    parent = obj.getParentGeoFeatureGroup()
    if parent:
        mesh.transform(parent.getGlobalPlacement().inverse().toMatrix())
    obj.Placement = App.Placement()
    obj.Mesh = mesh

    motion = json.loads(doc.R5.MotionGeometry)
    spec = {'part': obj.Name, 'world_bounds_mm': [RELIEF_MIN, RELIEF_MAX], 'removed_mm3': removed}
    motion['eye_pitch']['front_shell_relief'] = spec
    doc.R5.MotionGeometry = json.dumps(motion, ensure_ascii=False)
    return spec
