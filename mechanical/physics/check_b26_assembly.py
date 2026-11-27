"""Rigid step-by-step assembly check of the B26 168-step plan (the plan the assembly viewer shows).

Runs the B19-B25 assembly checker (part approaches, nut placement, bolt insertion and key access,
held nuts with their tools, camera feed, yaw driver access) on the exact B26 plan and hardware
seats the viewer uses, instead of the older B25 checker plan.

    python mechanical/physics/check_b26_assembly.py build/b26/cad mechanical/revisions/b24/hardware.json \
        mechanical/revisions/b24/hardware-spec.json mechanical/revisions/b26 build/b26/assembly-check.json \
        --source mechanical/revisions/b26/R5-B26-Assembly.FCStd
"""

from argparse import ArgumentParser
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'web/b19')]

import check_b19_assembly as C
import b25_preview as B25


# Contacts that the rigid checker flags but that are the design, with the reason. Only these exact
# part pairs in these steps are moved from issues to notes; anything else still blocks.
EXPECTED = {
    'a4-socket-fix': {('A4StationFastener1', 'A4StationFastener4'): 'the M3 x 30 threads into its own nut',
                      ('A4StationFastener5', 'A4StationFastener8'): 'the M3 x 30 threads into its own nut'},
    'a4-wago-wires': {('A4W35SocketCup', 'A4XT60ExternalSocket'): 'solder cup on the socket pin',
                      ('A4W36SocketCup', 'A4XT60ExternalSocket'): 'solder cup on the socket pin'},
    'a4-hatch-leads': {('A4W8', 'A4J2CupPositiveEnvelope'): 'wire end soldered in the plug cup',
                       ('A4W9', 'A4J2CupGroundEnvelope'): 'wire end soldered in the plug cup'},
    'a4-hub-plugs': {('A4J1FemaleEnvelope', 'HubBodyJ1'): 'mated plug envelope in its header',
                     ('A4J2FemaleEnvelope', 'HubBodyJ2'): 'mated plug envelope in its header',
                     ('A4J1FemaleEnvelope', 'HubPCB'): 'plug envelope slides on the board surface (< 1 mm3)',
                     ('A4J2FemaleEnvelope', 'HubPCB'): 'plug envelope slides on the board surface (< 1 mm3)'},
    'camera-nose-guide': {('CameraEatonHeadTie', 'Part073'): 'nylon tie strap flexes past the skull edge (0.1 mm3)'},
}


def triage(rows):
    for row in rows:
        allowed = EXPECTED.get(row['id'], {})
        kept = []
        for issue in row['issues']:
            pair = tuple(part.strip() for part in issue.split(' while ')[0].split('↔'))
            if len(pair) == 2 and pair in allowed:
                row['notes'].append(f'expected contact · {issue} · {allowed[pair]}')
            else:
                kept.append(issue)
        row['issues'] = kept
    return rows


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path)
    parser.add_argument('hardware', type=Path)
    parser.add_argument('spec', type=Path)
    parser.add_argument('revision_dir', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--hatch-paths', type=Path)
    parser.add_argument('--only', help='comma-separated step ids to report (all are still assembled)')
    args = parser.parse_args()

    original_world = C.World
    layout = json.loads((args.cad / 'cad_parts.json').read_text())

    class B26World(original_world):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.layout = layout
            catalog, heat, retainers = B25.setup(layout, self, args.revision_dir)
            self.b26_plan = B25.plan(layout, heat, retainers, self)
            self.b26_catalog = catalog
            self.setup_done = True

        def apply_b25_heat_set_screws(self, evidence=None):
            # B25.setup applies this revision's record; the checker's later default (B25) call is skipped.
            if not getattr(self, 'setup_done', False):
                super().apply_b25_heat_set_screws(evidence)

    worlds = []

    def make_world(*a, **k):
        world = B26World(*a, **k)
        worlds.append(world)
        return world

    C.World = make_world
    original_plan = C.assembly_plan
    C.assembly_plan = lambda revision, layout=None: (
        worlds[-1].b26_plan if worlds and hasattr(worlds[-1], 'b26_plan') else original_plan(revision, layout))
    hardware = json.loads(args.hardware.read_text())['hardware']
    spec = json.loads(args.spec.read_text())
    result = triage(C.run(args.cad, hardware, spec, 'b25', args.source, args.hatch_paths))
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + '\n')
    bad = [row['id'] for row in result if row['issues']]
    expected = sum(1 for row in result for note in row['notes'] if note.startswith('expected contact'))
    print(f'{len(result)} steps, {len(bad)} with blocking issues', bad, f'· {expected} expected contacts')
    if bad:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
