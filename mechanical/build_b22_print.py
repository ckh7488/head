"""Replace selected meshes in the native B21 P2S project with B22 parts."""

from argparse import ArgumentParser
from pathlib import Path

import trimesh

from build_b21_print import REVISIONS, build


BASE = REVISIONS / 'b21/R5-B21-P2S.3mf'
JAW_BEARING_STAY = '37_right_cheek_bearing_stay-B21.stl'


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--stl', action='append', required=True, metavar='B21_SOURCE=B22_STL')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    replacements = {}
    for entry in args.stl:
        source, separator, incoming = entry.partition('=')
        if not separator or not source or not incoming or source in replacements:
            parser.error(f'expected a distinct source filename and an STL path in {entry!r}')
        path = Path(incoming)
        replacements[source] = path.name, trimesh.load_mesh(path)
    build(args.output, replacements, args.report, source=BASE, revision='B22', without_ballast=True,
          normal_support=(JAW_BEARING_STAY,))
