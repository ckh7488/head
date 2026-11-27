"""Measure B27 temple relocation concepts on copies of the B26 world meshes."""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
from shutil import copytree

import numpy as np
import trimesh as tr


MOUNT_TRANSLATIONS = {
    'Part025': 6.2, 'EyePitchBearingL': 6.2, 'Part026': 6.2,
    'CradleMountFrameL': 6.2, 'CradleMountFrameLInsert': 6.2,
    'Part027': -7.8, 'EyePitchBearingR': -7.8, 'Part028': -7.8,
    'CradleMountFrameR': -7.8, 'CradleMountFrameRInsert': -7.8,
    'Part044': -2.7, 'EyePitchLinkHornPin': -2.7, 'EyePitchLinkCradlePin': -2.7,
    'Part057': 2.7, 'Part060': -2.7,
}


def smooth(values, lo, hi):
    t = np.clip((values-lo)/(hi-lo),0.,1.)
    return t*t*(3.-2.*t)


def band(values, start, in_start, in_end, end):
    return smooth(values,start,in_start)*(1.-smooth(values,in_end,end))


def frame_mounts(mesh):
    # Only the eye support seats move. The neck bearing axis and rear skull seats retain their locations.
    x,y,z = mesh.vertices.copy().T
    w = (smooth(np.abs(x),39.,59.2)*band(y,14.,21.,33.,40.)*
         band(z,135.,141.4,151.1,158.))
    mesh.vertices[:,0] = x + np.where(x < 0.,6.2,-7.8)*w


def shorten_cradle(mesh, right_delta):
    # Keep the eye axes and shorten around the eye-pitch pins, with a smaller move at the link pickup.
    x,y,_ = mesh.vertices.copy().T
    amount = np.where(x < 0.,6.2,-7.8+(right_delta+7.8)*smooth(y,-36.5,-32.5))
    mesh.vertices[:,0] = x + amount*smooth(np.abs(x),39.,58.)


def run(baseline, output, mode):
    layout=json.loads((baseline/'cad_parts.json').read_bytes())
    assert layout['source_sha256']=='2a50f5a128e886066cbee5a17bb285c53e91470169ff114774c941640e6bced0'
    output.mkdir(parents=True,exist_ok=False)
    copytree(baseline/'world',output/'world')
    paired=mode!='group'
    actuator=mode=='actuator'
    operations=MOUNT_TRANSLATIONS.copy()
    if paired:
        # The 0.1 mm change at the link retains the motor-side space for the inboard joint.
        shift = -7.8 if actuator else -2.6
        operations.update(Part044=shift,EyePitchLinkCradlePin=shift,EyePitchLinkHornPin=shift)
        mate_shapes={'Part019':frame_mounts,'Part024':lambda body:shorten_cradle(body,shift)}
    else:
        mate_shapes={}
    if actuator:
        for name in layout['world_motion']:
            if name in ('Part041','Part042','Part043','Part064') or name.startswith(
                    ('EyePitchStayFrame','EyePitchHornScrew','eyePitchHead','XL330EyePitch')):
                operations[name] = -7.8
            for side, delta in [('L',2.7),('R',-2.7)]:
                if name.startswith((f'BlinkPivotUpper{side}',f'BlinkPivotLower{side}')):
                    operations[name] = delta
    for part in sorted(operations.keys()|mate_shapes.keys()):
        path=output/'world'/f'{part}.stl'
        shape=tr.load_mesh(path)
        if part in mate_shapes:
            mate_shapes[part](shape)
        else:
            shape.apply_translation((operations[part],0.,0.))
        shape.export(path)
        layout['world_sha256'][part]=sha256(path.read_bytes()).hexdigest()
    layout['trial_from_sha256']=layout.pop('source_sha256')
    layout['trial']='Diagnostic stage-1 meshes; not a released FreeCAD assembly'
    layout['trial_x_translations_mm']=operations
    layout['trial_local_reshapes']=list(mate_shapes)
    (output/'cad_parts.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2),encoding='utf-8')
    print(mode,len(operations)+len(mate_shapes),'modified meshes',flush=True)


if __name__=='__main__':
    parser=ArgumentParser()
    parser.add_argument('baseline',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('mode',choices=('group','paired','actuator'))
    run(**vars(parser.parse_args()))
