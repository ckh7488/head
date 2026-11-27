"""Cut the right hatch-bar region (x 30-60, y 40-82, z -83.5 to -62) of the base cup as STEP.

    python mechanical/physics/cut_b26_hatch_region.py <assembly.FCStd> <out.step>
"""
import FreeCAD as App, Part, sys
from FreeCAD import Vector as V
src, out = sys.argv[1], sys.argv[2]
doc = App.openDocument(src)
s = doc.Part000.Shape.copy()
s.Placement = doc.Part000.getGlobalPlacement() if hasattr(doc.Part000,'getGlobalPlacement') else s.Placement
box = Part.makeBox(30, 42, 21.5, V(30, 40, -83.5))
c = s.common(box).removeSplitter()
b=c.BoundBox; print(len(c.Solids), round(c.Volume,1), [round(v,2) for v in (b.XMin,b.XMax,b.YMin,b.YMax,b.ZMin,b.ZMax)])
c.exportStep(out)
App.closeDocument(doc.Name)
