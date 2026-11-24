from argparse import ArgumentParser
from hashlib import file_digest
from pathlib import Path
import json
import numpy as np
import FreeCAD as App
import Part, Mesh
import manifold3d as md
import trimesh
from scipy.spatial.transform import Rotation
from build_b22_fused_skull import solid
from build_b25_jaw_retention import mesh_from_solid
from check_b25_jaw_retention import geometry
from scipy.optimize import linprog, minimize

LIMIT_MM = .10
SIZE_SCALE = .95
WARP_MM = .08
WARP_PER_MM = .002
NAMES = ('Jaw_36_left_jaw_servo_stay', 'Jaw_37_right_jaw_bearing_stay')
LOCAL_CASES = (
    ((-61.2531103515625, -18.31499931335449, 108.21255737304688), (-1., -1., -1.)),
    ((63.095, -5.81, 102.16938262939453), (-1., -1., 1.)),
)
SHELL_SIZE_MM = np.array((.2, .1, .2))
STAY_SIZE_MM = np.array((.1, .2, .2))
BOUNDARY_EPS_MM = 1e-6

O=np.array([0.,0.,103.5])
BORES=(('x',[-66,-59.55],[-32.5,103.5]), ('x',[62.55,69],[-8.75,103.5]),
       ('y',[-24.6,-19.5],[-68.6,103.5]))
ENDPOINTS=[]
for axis, ends, params in BORES:
    i='xyz'.index(axis)
    for end in ends:
        p=list(params)
        p.insert(i,end)
        ends = [j for j in range(3) if j!=i]
        ENDPOINTS.append((np.array(p),ends))

def coeff(p):
    arms=p-O
    return np.column_stack((np.eye(3), np.cross(np.eye(3),arms).T))

C=np.array([coeff(p)[inds] for p,inds in ENDPOINTS])
R=.03
CL=np.concatenate((C.reshape(-1,6),-C.reshape(-1,6)))

def allowed_for(p, toward):
    w=np.asarray(toward)@coeff(np.asarray(p))
    upper=linprog(-w,A_ub=CL,b_ub=[R]*len(CL),bounds=[(None,None)]*6,method='highs')
    feasible=minimize(lambda q:float(-w@q),upper.x*.7,
        constraints=[{'type':'ineq','fun':lambda q:R**2-np.sum((C@q)**2,axis=1)}],
        method='SLSQP',options={'ftol':1e-12,'maxiter':300})
    return -upper.fun,-feasible.fun,feasible.x,C@feasible.x


def read_parts(path):
    doc=App.openDocument(str(path.resolve()))
    out={p.Name:geometry(p) for p in doc.Objects if p.Name in ('Part073','Jaw_36_left_jaw_servo_stay','Jaw_37_right_jaw_bearing_stay')}
    App.closeDocument(doc.Name)
    return out
def box(low,high):
    return md.Manifold.cube(np.subtract(high,low)).translate(low)
def optimum(p,f):
    _,_,q,_=allowed_for(p,f)
    q*=.95
    R=Rotation.from_rotvec(q[3:]).as_matrix()
    cable=O+q[:3]-R@O
    T=np.column_stack((R,cable))
    errors=[float(np.linalg.norm((R@point+cable-point)[inds])) for point,inds in ENDPOINTS]
    assert max(errors)<=.030
    return T, errors

def shifted(shell,stay, p, df, ds, give_play, warp):
    q=p.copy()
    base_a=solid(shell)
    base_b=solid(stay)
    half=np.array([2.5,.95,2.5])
    pf=p-df
    ps=p-ds
    by=base_b ^ box(ps-half,ps+half)
    # Apply a local normal variation as one trial flatness field. Its print-plane distance
    # slope is 0.002 along each radial line and it decays to zero within the chosen radius.
    warped=shell.copy()
    radii=np.linalg.norm(warped.vertices[:,[0,2]]-pf[[0,2]],axis=1)
    moved=warped.vertices.copy()
    moved[:,1]-=np.maximum(warp-WARP_PER_MM*radii,0.)
    warped.vertices=moved
    modified=solid(warped)
    if modified.status()!=md.Error.NoError or not modified.volume()>0:
        raise ValueError('Warped shell mesh no longer valid')
    fx=(modified ^ box(pf-half,pf+half)).translate(df)
    by=by.translate(ds)
    A=modified+fx
    B=base_b+by
    T, play_errors=(np.column_stack((np.eye(3),np.zeros(3))),[0.]*6)
    if give_play:
        T,play_errors=optimum(ps,(0,1,0))
    B=B.transform(T)
    # Restrict expensive boolean to neighborhood with physical surfaces at the center;
    # the full assembled meshes determine point distances.
    region=box(q-2.1,q+2.1)
    outcome=(A ^ B) ^ region
    if outcome.is_empty() or outcome.volume()<=0:
        return {'full_warp_height_mm':warp,'play_enabled':give_play,'overlap_volume_mm3':0.}
    overlap=mesh_from_solid(outcome)
    sample=np.unique(np.vstack((overlap.vertices,overlap.triangles_center)),axis=0)
    patchA=mesh_from_solid(A)
    patchB=mesh_from_solid(B)
    # Each witness lies on the physical surface of the intruding body. The depth
    # is its Euclidean distance to the receiving solid's boundary while inside.
    points_A=trimesh.proximity.signed_distance(patchA,sample)
    points_B=trimesh.proximity.signed_distance(patchB,sample)
    aa=int(np.where(np.abs(points_B) <= BOUNDARY_EPS_MM, points_A, -np.inf).argmax())
    bb=int(np.where(np.abs(points_A) <= BOUNDARY_EPS_MM, points_B, -np.inf).argmax())
    assert abs(points_B[aa]) <= BOUNDARY_EPS_MM and abs(points_A[bb]) <= BOUNDARY_EPS_MM
    vals=(float(points_A[aa]),float(points_B[bb]))
    points=(sample[aa].tolist(),sample[bb].tolist())
    _, distances_a, _ = trimesh.proximity.closest_point(patchA, sample[[aa]])
    _, distances_b, _ = trimesh.proximity.closest_point(patchB, sample[[bb]])
    np.testing.assert_allclose(vals, [distances_a[0], distances_b[0]], atol=BOUNDARY_EPS_MM, rtol=0.)
    return {
      'full_warp_height_mm':warp,'warp_footprint_radius_mm':warp/WARP_PER_MM,
      'play_enabled':give_play,'play_endpoint_errors_mm':play_errors,
      'witness_solid_overlap_mm3':outcome.volume(), 'directed_sdf_depth_lower_mm':{'stay_into_shell':vals[0],'shell_into_stay':vals[1]},
      'depth_world_points':{'stay_into_shell':points[0],'shell_into_stay':points[1]},
      'source_surface_residual_mm':{'stay_into_shell':float(points_B[aa]),'shell_into_stay':float(points_A[bb])},
      'warp_center_world_xz_mm':pf[[0,2]].tolist(),
      'applied_shell_size_offset_world_mm':df.tolist(),
      'applied_stay_size_offset_world_mm':ds.tolist(),
      'play_transform_stay_matrix_3x4':T.tolist(),
      'shell_extent_changes_mm':(patchA.extents-shell.extents).tolist(),
      'dimensions_only_stay_extent_changes_mm':(mesh_from_solid(base_b+by).extents-stay.extents).tolist(),
      'vertex_count_of_intersection':len(overlap.vertices),
    }

if __name__=='__main__':
    parser = ArgumentParser(description='Measure B25 V5 stationary shell/stay intrusion witnesses.')
    parser.add_argument('candidate', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    meshes = read_parts(args.candidate)
    report = {'stationary_limit_mm':LIMIT_MM,'scope':(
        'Seated V5 trial. Directed depth witnesses measure Euclidean inward distance from a physical '
        'surface point of the intruding solid to the receiving solid boundary. '
        'Each reported depth is a lower bound of the maximum within the allowed input envelope.'),
        'dimensions_applied_fraction':SIZE_SCALE,
        'maximum_fitted_receiver_diametral_clearance_mm':2*R,
        'warp_slope_mm_per_mm':WARP_PER_MM,
        'cases':{}}
    with args.candidate.open('rb') as handle:
        report['candidate_cad_sha256'] = file_digest(handle,'sha256').hexdigest()
    for name, (point, signs) in zip(NAMES, LOCAL_CASES, strict=True):
        df = SIZE_SCALE * SHELL_SIZE_MM * np.array(signs)
        ds = -SIZE_SCALE * STAY_SIZE_MM * np.array(signs)
        result = shifted(meshes['Part073'], meshes[name], np.asarray(point), df, ds, True, WARP_MM)
        assert min(result['directed_sdf_depth_lower_mm'].values()) > LIMIT_MM
        report['cases'][name] = result
    args.output.write_text(json.dumps(report, indent=2)+'\n')
