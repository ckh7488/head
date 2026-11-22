"""Measure B25 tie-bar contacts through a full eye-yaw sweep."""

from argparse import ArgumentParser
import json
from pathlib import Path

import fcl
import numpy as np
import trimesh
from trimesh.collision import mesh_to_BVH

from check_head import pose

TIE_BAR = "Part037"
YAW_DEG = np.linspace(-20., 20., 801)


def sweep(directory):
    layout = json.loads((directory / "cad_parts.json").read_text())
    motions = layout["world_motion"]
    poses = {
        motion: np.array([pose(motion, (0., 0., yaw, 0., 0.), layout) for yaw in YAW_DEG])
        for motion in set(motions.values())
    }
    world = directory / "world"
    tie = trimesh.load_mesh(world / f"{TIE_BAR}.stl")
    tie_object = fcl.CollisionObject(mesh_to_BVH(tie))
    inverse = np.linalg.inv(poses[motions[TIE_BAR]])
    relative = {motion: inverse @ transforms for motion, transforms in poses.items()}
    distance_request = fcl.DistanceRequest()
    collision_request = fcl.CollisionRequest()
    pairs = {}
    for name, motion in motions.items():
        if name == TIE_BAR:
            continue
        mesh = trimesh.load_mesh(world / f"{name}.stl")
        if mesh.is_empty:
            continue
        transforms = relative[motion]
        corners = trimesh.bounds.corners(mesh.bounds)
        swept = corners @ transforms[:, :3, :3].transpose(0, 2, 1) + transforms[:, None, :3, 3]
        if np.any(swept.min(axis=(0, 1)) > tie.bounds[1]+1.) or np.any(
            swept.max(axis=(0, 1)) < tie.bounds[0]-1.
        ):
            continue

        other = fcl.CollisionObject(mesh_to_BVH(mesh))
        contacts = []
        gap = float("inf")
        for angle, transform in zip(YAW_DEG, transforms, strict=True):
            other.setTransform(fcl.Transform(transform[:3, :3], transform[:3, 3]))
            distance = fcl.distance(tie_object, other, distance_request, fcl.DistanceResult())
            gap = min(gap, max(0., distance))
            if distance < 1e-6 and fcl.collide(tie_object, other, collision_request, fcl.CollisionResult()):
                contacts.append(round(float(angle), 2))
        pairs[name] = {"minimum_mesh_gap_mm": round(gap, 6), "contact_angles_deg": contacts}

    return {"cad_sha256": layout["source_sha256"], "yaw_samples": len(YAW_DEG), "pairs": pairs}


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("cad", type=Path)
    parser.add_argument("report", type=Path)
    arguments = parser.parse_args()
    result = sweep(arguments.cad)
    arguments.report.write_text(json.dumps(result, indent=2) + "\n")
    hits = [part for part, pair in result["pairs"].items() if pair["contact_angles_deg"]]
    print(f"{result['yaw_samples']} yaw angles, {len(result['pairs'])} tie-bar pairs, contacts: {hits}")
    raise SystemExit(bool(hits))
