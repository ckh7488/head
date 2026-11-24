"""Sample the checked B25 harness paths for the wiring viewer."""
from argparse import ArgumentParser
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'mechanical/physics'), str(ROOT / 'mechanical')]

from check_b25_j2_a4_service import LEADS, poses, service_route
from wiring_motion import PowerLead, power_lead


def rounded(points):
    return [[round(float(value), 4) for value in point] for point in points]


def j2_points(actor, withdrawal, parking, drop):
    edges, _ = service_route(*LEADS[actor], withdrawal, parking, drop)
    points = []
    for edge in edges:
        samples = edge.discretize(Deflection=.025)
        points.extend(samples if not points else samples[1:])
    return rounded(points)


def export(layout, output):
    cad = json.loads(layout.read_text())
    report = json.loads((ROOT / 'mechanical/revisions/b25/a4-supply-recheck.json').read_text())
    service = report['combined_hatch_motion']
    check_states = poses()
    if len(check_states) != service['sample_count'] or check_states[-1][-1] != 30:
        raise ValueError('The displayed service pose range must match the B25 check record.')
    j1 = {id: PowerLead(**spec) for id, spec in report['five_volt_J1_hatch_route']['specs'].items()}
    frames = [{'phase': phase, 'withdrawal': withdrawal, 'parking': parking, 'drop': drop,
               'wires': {id: j2_points(id, withdrawal, parking, drop) for id in LEADS}}
              for phase, withdrawal, parking, drop in check_states]
    five_volt = [{id: rounded(power_lead(spec, drop)[0]) for id, spec in j1.items()}
                 for drop in range(31)]
    output.write_text(json.dumps({'cad': cad['source_sha256'], 'service': frames, 'power': five_volt},
                                 separators=(',', ':')) + '\n')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('layout', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    export(args.layout, args.output)
