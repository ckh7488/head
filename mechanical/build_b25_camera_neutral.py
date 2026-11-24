"""Update the FreeCAD assembly's neutral Eaton cable from the checked path."""

from argparse import ArgumentParser
import json
from pathlib import Path

import FreeCAD as App
import Mesh  # Register Mesh::Feature with FreeCAD.
import numpy as np
from shapely import Point
from trimesh.creation import sweep_polygon

from build_b25_jaw_retention import replace_mesh
from check_b25_camera_lower import CUT_LENGTH, DATA, REAR_RADIUS, lower_bight, reserve_loop
from check_b25_camera_upper import ENTRY, upper_at


def neutral_path():
    data = json.loads(DATA.read_text())
    fixed = np.asarray(data['fixed']['curve_mm'])
    heading = np.radians(data['fixed']['heading_deg'])
    turn = np.array(((np.cos(heading), np.sin(heading), 0.),
                     (-np.sin(heading), np.cos(heading), 0.), (0., 0., 1.)))
    rotor, _ = lower_bight(fixed[0] @ turn, ENTRY @ turn)
    rotor = rotor @ turn.T
    head, _ = upper_at(0., 0.)
    anchors = np.vstack((fixed[::-1], rotor[1:], head[1:]))
    length = np.linalg.norm(np.diff(anchors, axis=0), axis=1).sum()
    loop_start_y = fixed[-1, 1]
    loop_y = loop_start_y + (CUT_LENGTH - length - np.pi * REAR_RADIUS) / 2
    return np.vstack((reserve_loop(loop_y)[:-1], anchors))


def build(source, output):
    points = neutral_path()
    cable = sweep_polygon(Point(0., 0.).buffer(1.4, quad_segs=8), points, engine='manifold')
    if not cable.is_volume or cable.body_count != 1:
        raise ValueError('Neutral camera cable must be one closed mesh')
    if abs(np.linalg.norm(np.diff(points, axis=0), axis=1).sum() - CUT_LENGTH) > .05:
        raise ValueError('Neutral camera cable is outside the cut length')
    doc = App.openDocument(str(source.resolve()))
    try:
        replace_mesh(doc.EatonCableNeutral, cable)
        doc.recompute()
        doc.saveAs(str(output.resolve()))
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    build(**vars(parser.parse_args()))
