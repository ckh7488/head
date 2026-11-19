"""Fit a USB camera's lens parameters from several checkerboard photographs."""
from argparse import ArgumentParser
from glob import glob
import json
from pathlib import Path

import cv2
import numpy as np


def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('photos',type=Path,nargs='+')
    parser.add_argument('--columns',type=int,default=9,help='Inner corners across')
    parser.add_argument('--rows',type=int,default=6,help='Inner corners down')
    parser.add_argument('--square-mm',type=float,default=24.)
    parser.add_argument('--output',type=Path,default=Path('camera.json'))
    args=parser.parse_args()
    if args.columns<3 or args.rows<3 or not 0<args.square_mm<1000:
        parser.error('A valid inner-corner grid and square size are required.')
    grid=(args.columns,args.rows)
    object_grid=np.zeros((grid[0]*grid[1],3),np.float32)
    object_grid[:,:2]=np.mgrid[0:grid[0],0:grid[1]].T.reshape(-1,2)*args.square_mm
    objects,images=[],[]
    size=None
    photos = [Path(hit) for pattern in args.photos for hit in sorted(glob(str(pattern)))]
    for path in photos:
        photo=cv2.imread(str(path),cv2.IMREAD_GRAYSCALE)
        if photo is None:
            print(f'Skipped unreadable photo {path}')
            continue
        current=(photo.shape[1],photo.shape[0])
        if size is not None and current!=size:
            raise SystemExit('Use the same image resolution for every view.')
        found,corners=cv2.findChessboardCornersSB(photo,grid,cv2.CALIB_CB_NORMALIZE_IMAGE)
        if found:
            size=current
            images.append(corners)
            objects.append(object_grid.copy())
        else:
            print(f'No complete checkerboard in {path}')
    if len(images)<10:
        raise SystemExit('Use at least 10 complete views from different angles.')
    rms,matrix,dist,_,_=cv2.calibrateCamera(objects,images,size,None,None)
    data={'width':size[0],'height':size[1],'camera_matrix':matrix.tolist(),
          'dist_coeffs':dist.ravel().tolist(),'reprojection_px':rms,'views':len(images)}
    args.output.write_text(json.dumps(data,indent=2)+'\n')
    print(f'{len(images)} views, RMS {rms:.3f} px, {args.output}')


if __name__=='__main__':
    main()
