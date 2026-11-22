"""Measure admissible local manufacturing witnesses in the B25 head world frame."""
from argparse import ArgumentParser
from itertools import product
from hashlib import file_digest
from pathlib import Path
import json
import FreeCAD as App, Part, Mesh
import fcl
import numpy as np
import trimesh as tr
import manifold3d as md
from build_b22_fused_skull import solid
from check_b25_jaw_retention import geometry, collision
from build_b25_jaw_relief_trials import LEFT_STAY, RIGHT_STAY

FIXED={
    'Part019': (.2,.1,.2),
    'Part011': (.2,.1,.2),
    'Part073': (.2,.1,.2),
}
STAY=(.1,.2,.2)
FACTOR=.95
def manifold_box(low,high):
    return md.Manifold.cube(np.subtract(high,low)).translate(low)
def digest(path):
    with path.open('rb') as g:
        return file_digest(g,'sha256').hexdigest()
def overlap_box(mesh_fixed,mesh_moving,T,df,dm,point,width):
    base_fix=solid(mesh_fixed)
    base_move=solid(mesh_moving)
    I=np.linalg.inv(T)
    source_fix=point-df
    source_move=I[:3,:3]@(point-dm)+I[:3,3]
    clip_fix=manifold_box(source_fix-width,source_fix+width)
    clip_move=manifold_box(source_move-width,source_move+width)
    moved_loc=(base_move^clip_move).transform(T[:3,:]).translate(dm)
    fixed_loc=(base_fix^clip_fix).translate(df)
    volume=(fixed_loc^moved_loc).volume()
    now_fix=base_fix+fixed_loc
    # Check the as-printed dimensions in the original, unrotated print frame.
    R=T[:3,:3]
    now_move=base_move+(base_move^clip_move).translate(R.T@dm)
    original_fix=np.reshape(base_fix.bounding_box(),(2,3))
    original_moving=np.reshape(base_move.bounding_box(),(2,3))
    diff_f=np.ptp(np.reshape(now_fix.bounding_box(),(2,3)),axis=0)-np.ptp(original_fix,axis=0)
    diff_m=np.ptp(np.reshape(now_move.bounding_box(),(2,3)),axis=0)-np.ptp(original_moving,axis=0)
    return volume, diff_f, diff_m

def fcl_distance(fixed, moving):
    return fcl.distance(fixed,moving,fcl.DistanceRequest(),fcl.DistanceResult())
def set_pose(fixed,moving,T,df,dm):
    fixed.setTranslation(df)
    moving.setTransform(fcl.Transform(T[:3,:3].copy(), T[:3,3]+dm))

def run_pair(mesh_F,mesh_M,fixed_name,stages,pitch):
    objects=collision(mesh_F),collision(mesh_M)
    fixed,moving=objects
    best=(np.inf,None)
    for stage in stages:
        T=tr.transformations.rotation_matrix(np.radians(stage),(1,0,0),(0.,0.,112.)) if pitch else np.eye(4)
        if not pitch:
            T[2,3]=-stage
        for signs in product((-1,1), repeat=3):
            direction=np.array(signs)
            df=FACTOR*np.array(FIXED[fixed_name])*direction
            # Make the moving part's size error in its print axes.
            dm=-T[:3,:3]@(FACTOR*np.array(STAY)*direction)
            set_pose(fixed,moving,T,df,dm)
            distance=fcl_distance(fixed,moving)
            if distance<best[0]:
                best=distance,(T.copy(),df,dm,stage,signs)
    d,(T,df,dm,stage,signs)=best
    set_pose(fixed,moving,T,df,dm)
    result=fcl.DistanceResult()
    fcl.distance(fixed,moving,fcl.DistanceRequest(enable_nearest_points=True),result)
    witness=np.array(result.nearest_points)
    result_hit=fcl.CollisionResult()
    fcl.collide(fixed,moving,fcl.CollisionRequest(enable_contact=True,num_max_contacts=24),result_hit)
    # Use a local piece around each exact contact without shifting unrelated holes or datums.
    cell_volume=0.0
    dims_f,dims_m=None,None
    p=witness.mean(axis=0)
    if result_hit.is_collision:
        candidates=[c.pos for c in result_hit.contacts]
        for p in candidates[:4]:
            volume,f,m=overlap_box(mesh_F,mesh_M,T,df,dm,np.asarray(p),3.5)
            if volume>cell_volume:
                cell_volume,dims_f,dims_m=volume,f.tolist(),m.tolist()
            if cell_volume > .001:
                break
    return {'stage_deg' if pitch else 'stage_down_mm':float(stage),'nearness_mm':float(d),'local_contact_point_mm':p.tolist(),
            'factor':FACTOR,'axis_signs':signs,'fixed_local_size_shift_mm':df.tolist(),
            'stay_local_size_shift_mm':(T[:3,:3].T@dm).tolist(),'exact_local_overlap_mm3':cell_volume,
            'fixed_extent_change_mm':dims_f,'stay_extent_change_mm':dims_m}

def main():
    p=ArgumentParser(description=__doc__)
    p.add_argument('cad',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--quick',action='store_true')
    args=p.parse_args()
    doc=App.openDocument(str(args.cad.resolve()))
    try:
        meshes = {name: geometry(doc.getObject(name)) for name in (*FIXED, LEFT_STAY, RIGHT_STAY)}
    finally:
        App.closeDocument(doc.Name)
    trials={}
    for fixed in FIXED:
        for moving in (LEFT_STAY, RIGHT_STAY):
            for pitch in ((False,True) if fixed=='Part011' else (False,)):
                if pitch:
                    stages=np.linspace(-17.21,7.13,25 if args.quick else 245)
                elif args.quick:
                    stages=np.r_[np.linspace(0,2,9),5.,8.5,22.5]
                else:
                    stages=np.r_[np.linspace(0,7,36),np.arange(7.5,76.1,.5)]
                result=run_pair(meshes[fixed],meshes[moving],fixed,stages,pitch)
                key=f'{fixed} / {moving} / {"pitch" if pitch else "jaw insertion"}'
                print(key,result,flush=True)
                trials[key]=result
    result={'source_cad_sha256':digest(args.cad),
            'scope':'95% of permitted directional print sizes in each part frame. Overlaps come from original plus displaced local pieces; the untouched part and its locating features are not moved. No plate warp included in witness.',
            'cases':trials}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
    main()
