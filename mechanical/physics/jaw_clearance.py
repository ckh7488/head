"""Check clearance of the original B2 tooth surfaces under positioning errors."""
from argparse import ArgumentParser
from itertools import product
from pathlib import Path
import json

import numpy as np
import trimesh
from trimesh.collision import CollisionManager


def incisors(mesh, upper):
    centers=mesh.triangles_center
    low,high=(40,57) if upper else (29,49)
    side,back=42.0,-48.0
    region=(np.abs(centers[:,0])<=side) & (centers[:,1]<back) & (centers[:,2]>=low) & (centers[:,2]<=high)
    if np.count_nonzero(region)<100:
        raise ValueError('Unexpected tooth zone geometry')
    return mesh.submesh([np.flatnonzero(region)],append=True,repair=False)


def inspect(input_dir):
    source=json.loads((input_dir/'cad_parts.json').read_text())
    pivot=source['jaw_pivot_mm']
    upper=trimesh.load_mesh(input_dir/'Part073.stl')
    lower=trimesh.load_mesh(input_dir/'Jaw_30_moving_jaw.stl')
    for part in (upper,lower):
        if not part.is_volume:
            raise ValueError('Tooth meshes must be closed oriented meshes before trimming')
    upper_tooth=incisors(upper,True)
    lower_tooth=incisors(lower,False)
    targets=CollisionManager()
    targets.add_object('upper teeth',upper_tooth)
    shell=CollisionManager()
    shell.add_object('upper shell',upper)
    results=[]
    angles=sorted(set(range(15)) | {0.25,0.50,0.75,1.25,1.5,1.75})
    for z_offset,angle_error in product((-.4,0,.4),(-.7,0,.7)):
        for request in angles:
            tx=trimesh.transformations.rotation_matrix(np.radians(request+angle_error),(1,0,0),pivot)
            tx[2,3]+=z_offset
            collide=targets.in_collision_single(lower_tooth,transform=tx)
            dist=targets.min_distance_single(lower_tooth,transform=tx)
            other=shell.in_collision_single(lower,transform=tx)
            results.append({'jaw_deg':request,'hinge_vertical_mm':z_offset,'neutral_error_deg':angle_error,
                            'tooth_intersect':collide,'tooth_separation_mm':max(0.,float(dist)),
                            'upper_shell_intersect':other})
    nominal=[r for r in results if r['hinge_vertical_mm']==r['neutral_error_deg']==0]
    assert len(nominal)==len(angles)
    minima=[]
    for angle in angles:
        trials=[r for r in results if r['jaw_deg']==angle]
        minima.append({'opening_deg':angle,'min_tooth_gap_mm':min(r['tooth_separation_mm'] for r in trials),
                       'sampled_shell_collision':any(r['upper_shell_intersect'] for r in trials)})
    return {'cad_sha256':source['source_sha256'],'samples':results,'positioning_envelope':minima,
            'surface_triangles':[len(upper_tooth.faces),len(lower_tooth.faces)]}


if __name__=='__main__':
    p=ArgumentParser(description=__doc__)
    p.add_argument('cad',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    d=inspect(args.cad)
    (args.output/'jaw_clearance_results.json').write_text(json.dumps(d,indent=2))
    print('Neutral pose at each positioning offset:')
    for row in d['samples']:
        if row['jaw_deg']==0:print(row)
