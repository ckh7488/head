"""Represent the specified Phoenix 1715721 terminal at its installed height."""

from build_b19_review_fixes import replace
from export_cad import world_shape
from primitives import box


J2_INSTALLED_HEIGHT = 13.8
J2_SPEC = 'https://www.phoenixcontact.com/en-pc/products/pcb-terminal-block-mkds-15-2-508-1715721'


def j2_envelope(doc):
    # Preserve the conservative original XY envelope and anchor to the PCB face.
    b = world_shape(doc.HubBodyJ2).BoundBox
    pcb_top = world_shape(doc.HubPCB).BoundBox.ZMax
    if abs(b.ZMin-pcb_top) > .01 or not (10.1 < b.XLength < 10.4 and 9.7 < b.YLength < 10.):
        raise ValueError('J2 must be the Phoenix MKDS 1,5/2-5,08 on top of the servo-hub PCB')
    return box(b.XMin, b.XMax, b.YMin, b.YMax, pcb_top, pcb_top+J2_INSTALLED_HEIGHT)


def apply(doc):
    body = j2_envelope(doc)
    replace(doc.HubBodyJ2, body)
    doc.HubBodyJ2.Label = 'J2 · Phoenix 1715721 · 13.8 mm above PCB'
    return {'part': 'HubBodyJ2', 'installed_height_mm': J2_INSTALLED_HEIGHT, 'datasheet': J2_SPEC}
