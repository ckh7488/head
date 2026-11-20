"""Seated overlap of every pair of world meshes (export_cad.py --world), including pairs that move together."""
import sys, json, numpy as np, trimesh, fcl, itertools
from pathlib import Path
cad=Path(sys.argv[1]); info=json.loads((cad/'cad_parts.json').read_text())
parts={p['name']:p for p in (info['parts'] if 'parts' in info else info.values()) if isinstance(p,dict) and 'name' in p}
meshes={}
for f in sorted((cad/'world').glob('*.stl')):
    m=trimesh.load(f, force='mesh')
    if isinstance(m, trimesh.Trimesh) and len(m.faces): meshes[f.stem]=m
print(len(meshes), flush=True)
def bvh(m):
    o=fcl.BVHModel(); o.beginModel(len(m.vertices),len(m.faces)); o.addSubModel(m.vertices,m.faces); o.endModel(); return fcl.CollisionObject(o)
objs={k:bvh(m) for k,m in meshes.items()}
names=list(meshes); out=[]
for a,b in itertools.combinations(names,2):
    A,B=meshes[a],meshes[b]
    if np.any(A.bounds[1]<B.bounds[0]) or np.any(B.bounds[1]<A.bounds[0]): continue
    if not fcl.collide(objs[a],objs[b],fcl.CollisionRequest(),fcl.CollisionResult()): continue
    try:
        i=A.intersection(B); v=0. if i.is_empty else float(i.volume)
        bb=None if i.is_empty else i.bounds.round(2).tolist()
    except Exception as e:
        v=None; bb=str(e)
    if v is None or v>0.05:
        ma=parts.get(a,{}).get('motion'); mb=parts.get(b,{}).get('motion')
        out.append({'a':a,'b':b,'la':parts.get(a,{}).get('label'),'lb':parts.get(b,{}).get('label'),'ma':ma,'mb':mb,'mm3':v,'bounds':bb})
        print(out[-1], flush=True)
json.dump(out,open(sys.argv[2],'w'),indent=1,ensure_ascii=False)
print('DONE',len(out))
