"""Swept volumes of the B21 holding tools against each assembly context."""

from itertools import product

import fcl
import manifold3d as md
import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
import trimesh as tr
from trimesh.collision import mesh_to_BVH


NUT_HEIGHT = {2: 1.6, 3: 2.4}
SOCKET_RADII = {2: (3.70, 2.38), 3: (4.65, 3.25)}
SOCKET_DEPTH_MM = 5.6
SOCKET_LENGTH_MM = 22.
OVERLAP_MM3 = .05


def arm_frame(axis, outward, origin):
    frame = np.eye(4)
    frame[:3, :3] = np.column_stack((np.cross(outward, axis), outward, axis))
    frame[:3, 3] = origin
    return frame


def translated_profile(profile, length):
    outline = np.asarray(profile.exterior.coords)
    axis = np.array([0., length])
    return unary_union([profile, *[Polygon([a, b, b+axis, a+axis])
                                    for a, b in zip(outline[:-1], outline[1:])
                                    if abs(a[0]-b[0]) > 1e-9]])


def manifold(mesh):
    return md.Manifold(md.Mesh(np.asarray(mesh.vertices, np.float32), np.asarray(mesh.faces, np.uint32)))


class ToolCheck:
    def __init__(self, world, hardware):
        self.world = world
        self.wrenches = {row['size']: (Polygon(row['profile']), row['thickness'])
                         for row in hardware if row.get('tool') and row['type'] == 'spanner'}
        self.geometry = {}
        self.solids = {}
        self.nut_phases = {}
        self.nut_variants = {}
        self.routes = {}

    def installed(self, names, target):
        for name in sorted(set(names)):
            if name == target:
                continue
            if name in self.nut_phases:
                yield self.nut_at(name, self.nut_phases[name])
                continue
            mesh = self.world.mesh(name)
            if mesh is None:
                continue
            if name not in self.geometry or self.geometry[name][0] is not mesh:
                self.geometry[name] = mesh, fcl.CollisionObject(mesh_to_BVH(mesh))
            yield name, *self.geometry[name]

    @staticmethod
    def outside(origin, direction, obstacles):
        # AABB support along the approach direction. Start beyond every fitted obstacle.
        far = max((np.maximum(mesh.bounds[0]*direction, mesh.bounds[1]*direction).sum()
                   -origin @ direction for _, mesh, _ in obstacles), default=0.)
        return max(0., far) + 5.

    def blockage(self, tool, obstacles):
        moving = fcl.CollisionObject(mesh_to_BVH(tool))
        volume = None
        lo, hi = tool.bounds
        for name, mesh, fixed in obstacles:
            low, high = mesh.bounds
            if np.any(hi < low) or np.any(lo > high):
                continue
            intersects = fcl.collide(moving, fixed, fcl.CollisionRequest(), fcl.CollisionResult())
            contained = np.all((lo <= low) & (hi >= high)) or np.all((low <= lo) & (high >= hi))
            if intersects or contained:
                if not mesh.is_volume:
                    if not intersects:
                        continue
                    return name, 'unknown'
                if volume is None:
                    volume = manifold(tool)
                key = id(mesh)
                if key not in self.solids:
                    self.solids[key] = mesh, manifold(mesh)
                _, other = self.solids[key]
                if volume.status() != md.Error.NoError or other.status() != md.Error.NoError:
                    return name, 'unknown'
                if (volume ^ other).volume() > OVERLAP_MM3:
                    return name, 'fail'
        return None

    def nut_at(self, name, degrees):
        key = (name, degrees)
        if key not in self.nut_variants:
            row = self.world.rows[name]
            mesh = self.world.reference_nut(name).copy()
            if degrees:
                mesh.apply_transform(tr.transformations.rotation_matrix(
                    np.radians(degrees), row['axis'], row['seat']))
            self.nut_variants[key] = name, mesh, fcl.CollisionObject(mesh_to_BVH(mesh))
        return self.nut_variants[key]

    def require_nut_phase(self, name, angle):
        self.nut_phases[name] = angle
        self.world.accept_nut(name, self.nut_at(name, angle)[1])

    def wrench(self, row, obstacles):
        profile, thickness = self.wrenches[row['size']]
        axis = np.asarray(row['axis'], float)
        origin = np.asarray(row['seat'])
        height = NUT_HEIGHT[row['size']]
        u, v, _ = tr.geometry.align_vectors([0., 0., 1.], axis)[:3, :3].T
        for angle, depth in product(range(0, 360, 30), (height-thickness-.15, (height-thickness)/2, .24)):
            phase = (-angle + 30) % 60 - 30
            a = np.radians(angle)
            outward = u*np.sin(a) + v*np.cos(a)
            seat = origin + depth*axis
            length = self.outside(seat, outward, obstacles)
            area = translated_profile(profile, length)
            tool = tr.creation.extrude_polygon(area, thickness)
            tool.apply_transform(arm_frame(axis, outward, seat))
            yield tool, {'tool': 'spanner', 'axis': axis.tolist(), 'outward': outward.round(6).tolist(),
                         'seat_mm': seat.round(3).tolist(), 'travel_mm': round(length, 3), 'nut_rotation_deg': phase,
                         'head_width_mm': profile.bounds[2]-profile.bounds[0], 'thickness_mm': thickness}

    def socket(self, row, obstacles):
        outer, inner = SOCKET_RADII[row['size']]
        axis = np.asarray(row['axis'], float)
        origin = np.asarray(row['seat'])
        height = NUT_HEIGHT[row['size']]
        for sign in (1., -1.):
            outward = sign*axis
            seat = origin + (height if sign > 0 else 0)*axis - height/2*outward
            travel = self.outside(seat, outward, obstacles)
            length = SOCKET_LENGTH_MM + travel
            swept = tr.creation.revolve([(inner, 0), (outer, 0), (outer, length), (0, length),
                                         (0, SOCKET_DEPTH_MM), (inner, SOCKET_DEPTH_MM), (inner, 0)], sections=48)
            swept.apply_transform(tr.geometry.align_vectors([0., 0., 1.], outward))
            swept.apply_translation(seat)
            yield swept, {'tool': 'socket', 'axis': axis.tolist(), 'outward': outward.tolist(),
                          'seat_mm': seat.round(3).tolist(), 'travel_mm': round(travel, 3),
                          'outside_diameter_mm': 2*outer, 'body_length_mm': SOCKET_LENGTH_MM}

    def socket_over_lip(self, row, obstacles, inset_mm):
        outer, inner = SOCKET_RADII[row['size']]
        axis = np.asarray(row['axis'], float)
        up = np.array([0., 0., 1.])
        if abs(axis @ up) > 1e-9:
            raise ValueError('Over-the-lip socket route requires a horizontal screw axis')
        seat = np.asarray(row['seat']) + axis*NUT_HEIGHT[row['size']]/2
        lowered = seat + inset_mm*axis
        vertical = self.outside(lowered, up, obstacles)
        length = SOCKET_LENGTH_MM + inset_mm
        dock = tr.creation.revolve([(inner, 0), (outer, 0), (outer, length), (0, length),
                                    (0, SOCKET_DEPTH_MM), (inner, SOCKET_DEPTH_MM), (inner, 0)], sections=48)
        dock.apply_transform(tr.geometry.align_vectors([0., 0., 1.], axis))
        dock.apply_translation(seat)
        # The full outer body must clear on the vertical leg before the socket meets the nut.
        capsule = LineString([(0., 0.), (0., vertical)]).buffer(outer/np.cos(np.pi/64), quad_segs=16)
        lowering = tr.creation.extrude_polygon(capsule, SOCKET_LENGTH_MM)
        lowering.apply_transform(arm_frame(axis, up, lowered))
        swept = tr.boolean.union([lowering, dock], engine='manifold')
        yield swept, {'tool': 'socket', 'axis': axis.tolist(), 'outward': axis.tolist(),
                      'seat_mm': seat.round(3).tolist(), 'travel_mm': round(inset_mm+vertical, 3),
                      'outside_diameter_mm': 2*outer, 'body_length_mm': SOCKET_LENGTH_MM,
                      'waypoints_mm': np.array([lowered+up*vertical, lowered, seat]).round(3).tolist()}

    def hold(self, target, installed, modes, rotated_entry=None, socket_inset_mm=None):
        self.routes.pop(target, None)
        row = self.world.rows.get(target)
        if row is None or row['type'] != 'nut' or row.get('size') not in NUT_HEIGHT:
            return {'status': 'unknown', 'reason': 'no typed nut geometry'}
        obstacles = tuple(self.installed(installed, target))
        failures = {}
        for mode in modes:
            if mode not in ('spanner', 'socket') or (mode == 'spanner' and row['size'] not in self.wrenches):
                failures[mode] = {'unknown': 'no measured tool profile'}
                continue
            if mode == 'spanner':
                routes = self.wrench(row, obstacles)
            elif socket_inset_mm is None:
                routes = self.socket(row, obstacles)
            else:
                routes = self.socket_over_lip(row, obstacles, socket_inset_mm)
            blockers = {}
            for tool, route in routes:
                phase = route.get('nut_rotation_deg', self.nut_phases.get(target, 0))
                if self.nut_phases.get(target, phase) != phase:
                    continue
                nut = self.nut_at(target, phase)
                blocker = self.blockage(nut[1], obstacles) or self.blockage(tool, (*obstacles, nut))
                if blocker is None:
                    if phase and rotated_entry is not None and not rotated_entry(nut[1]):
                        blockers.setdefault('fail', set()).add(f'{target} entry at {phase} degrees')
                        continue
                    if mode == 'spanner':
                        self.require_nut_phase(target, phase)
                    self.routes[target] = tool, route
                    return {'status': 'pass', **route}
                name, status = blocker
                blockers.setdefault(status, set()).add(name)
            failures[mode] = {status: sorted(parts) for status, parts in blockers.items()}
        status = 'unknown' if any('unknown' in value for value in failures.values()) else 'fail'
        return {'status': status, 'blockers': failures}

    def hold_together(self, first, second):
        if first not in self.routes or second not in self.routes:
            return {'status': 'unknown', 'reason': 'one or both individual tool routes are missing'}
        for held, moving in ((first, second), (second, first)):
            _, route = self.routes[held]
            if route['tool'] != 'spanner':
                return {'status': 'unknown', 'reason': 'paired access is modelled for spanners'}
            profile, thickness = self.wrenches[self.world.rows[held]['size']]
            seated = tr.creation.extrude_polygon(profile, thickness)
            seated.apply_transform(arm_frame(np.asarray(route['axis']), np.asarray(route['outward']),
                                             np.asarray(route['seat_mm'])))
            fixture = fcl.CollisionObject(mesh_to_BVH(seated))
            swept, _ = self.routes[moving]
            if self.blockage(swept, ((held, seated, fixture),)) is None:
                return {'status': 'pass', 'insertion_order': [held, moving]}
        return {'status': 'fail', 'reason': 'the swept tools interfere with each other'}

    def hold_and_drive(self, nut, driver):
        if nut not in self.routes:
            return {'status': 'unknown', 'reason': 'holding route missing'}
        sweep, _ = self.routes[nut]
        obstacle = fcl.CollisionObject(mesh_to_BVH(driver))
        collision = self.blockage(sweep, (('driver', driver, obstacle),))
        if collision is not None:
            return {'status': collision[1], 'reason': 'holding-tool sweep meets the straight key'}
        return {'status': 'pass', 'driver_axis_independent': True}
