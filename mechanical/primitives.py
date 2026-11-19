from FreeCAD import Vector as V
import MeshPart
import Part


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1-x0, y1-y0, z1-z0, V(x0, y0, z0))


def cylinder(radius, height, start, direction=(0, 0, 1)):
    return Part.makeCylinder(radius, height, V(*start), V(*direction))


def holes(shape, radius, depth, centres, direction=(0, 0, 1)):
    return shape.cut([cylinder(radius, depth, point, direction) for point in centres])


def print_mesh(shape, path, direction=None):
    model = shape.copy()
    if direction == 'x+':
        model.rotate(V(0, 0, 0), V(0, 1, 0), -90)
    elif direction == 'x-':
        model.rotate(V(0, 0, 0), V(0, 1, 0), 90)
    elif direction == 'y+':
        model.rotate(V(0, 0, 0), V(1, 0, 0), 90)
    elif direction == 'z-':
        model.rotate(V(0, 0, 0), V(1, 0, 0), 180)
    mesh = MeshPart.meshFromShape(Shape=model, LinearDeflection=.075, AngularDeflection=.10, Relative=False)
    bound = mesh.BoundBox
    mesh.translate(-bound.Center.x, -bound.Center.y, -bound.ZMin)
    mesh.write(str(path))
