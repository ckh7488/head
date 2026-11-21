"""Clear the left eyelid edge inside the stock front shell."""

import json

import FreeCAD as App
import Mesh
import manifold3d as md
import numpy as np
import trimesh

from export_cad import world_mesh


RELIEFS = (
    ('left', (-55.20, -30.96, 127.95), (-54.14, -28.97, 129.58)),
)


def cut_shell(stock):
    shell = md.Manifold(md.Mesh(
        np.ascontiguousarray(stock.vertices, dtype=np.float32),
        np.ascontiguousarray(stock.faces, dtype=np.uint32),
    ))
    edited = shell
    regions = []
    for side, lower, upper in RELIEFS:
        cutter = md.Manifold.cube(np.subtract(upper, lower)).translate(lower)
        carved = edited - cutter
        removed = edited.volume() - carved.volume()
        if removed <= 0.:
            raise ValueError(f'{side} blink relief does not touch the stock shell')
        regions.append({'side': side, 'world_bounds_mm': [lower, upper], 'removed_mm3': removed})
        edited = carved
    native = edited.to_mesh()
    result = trimesh.Trimesh(vertices=native.vert_properties[:, :3], faces=native.tri_verts, process=False)
    if (edited.status() != md.Error.NoError or not result.is_volume or result.body_count != 1
            or not np.allclose(stock.bounds, result.bounds, atol=1e-5, rtol=0.)):
        raise ValueError('Blink relief must preserve a single closed front shell and its stock envelope')
    return result, regions


def apply(doc):
    obj = doc.Part073
    points, triangles = world_mesh(obj).Topology
    stock = trimesh.Trimesh([tuple(point) for point in points], triangles)
    cut, regions = cut_shell(stock)
    mesh = Mesh.Mesh(cut.triangles.tolist())
    parent = obj.getParentGeoFeatureGroup()
    if parent:
        mesh.transform(parent.getGlobalPlacement().inverse().toMatrix())
    obj.Placement = App.Placement()
    obj.Mesh = mesh

    geometry = json.loads(doc.R5.MotionGeometry)
    spec = {'part': obj.Name, 'regions': regions, 'removed_mm3': sum(row['removed_mm3'] for row in regions)}
    geometry['blink_shell_relief'] = spec
    doc.R5.MotionGeometry = json.dumps(geometry, ensure_ascii=False)
    return spec
