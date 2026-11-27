"""Screen the baseline yoke rays that fall outside generous anatomy projections."""
from argparse import ArgumentParser
from itertools import product
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt
import trimesh as tr
from trimesh.ray.ray_pyembree import RayMeshIntersector

from check_b27_skull_cover import Export, ROOT, SPEC, in_zone, view_rays


def run(baseline, report):
    spec=json.loads(SPEC.read_bytes())
    export=Export(baseline)
    meshes, ids = [], []
    for name in export.motion:
        mesh=export.mesh(name)
        if len(mesh.faces):
            meshes.append(mesh)
            ids.extend([name=='Part011']*len(mesh.faces))
    yoke=np.array(ids)
    nominal=RayMeshIntersector(tr.util.concatenate(meshes))
    source_names = [*spec['anatomy']['cranium'].values(),*spec['anatomy']['temple_fill'].values(),spec['anatomy']['mandible']]
    reference=RayMeshIntersector(tr.util.concatenate([tr.load_mesh(ROOT/name) for name in source_names]))
    step=spec['views']['step_mm']
    margin=spec['anatomy']['outward_bulge_max_mm']+step
    rows=[]
    for side, label in ((1,'right'),(-1,'left')):
        for yaw, tilt in product(spec['views']['yaw_deg'],spec['views']['tilt_deg']):
            o,d,shape=view_rays(spec,side,yaw,tilt)
            xyz, ix, faces=nominal.intersects_location(o,d,multiple_hits=False)
            mask=yoke[faces] & in_zone(xyz,spec,side)
            visible=ix[mask]
            _, silhouette,_=reference.intersects_location(o,d,multiple_hits=False)
            empty=np.ones(shape[0]*shape[1],dtype=bool)
            empty[silhouette]=False
            distance=step*distance_transform_edt(empty.reshape(shape)).ravel()
            outside=visible[distance[visible]>margin]
            row={'side':label,'yaw_deg':yaw,'tilt_deg':tilt,'yoke_exposed_mm2':round(len(visible)*step**2,2),
                 'yoke_outside_reference_padding_mm2':round(len(outside)*step**2,2)}
            rows.append(row)
    report.write_text(json.dumps({'reference_padding_mm':margin,'sheet_sampling_mm':step,'views':rows},indent=2),encoding='utf8')
    for side in ('right','left'):
        vals=[r['yoke_outside_reference_padding_mm2'] for r in rows if r['side']==side]
        print(side,'outside-reference max and sum',max(vals),round(sum(vals),2),flush=True)


if __name__=='__main__':
    parser=ArgumentParser()
    parser.add_argument('baseline',type=Path)
    parser.add_argument('report',type=Path)
    run(**vars(parser.parse_args()))
