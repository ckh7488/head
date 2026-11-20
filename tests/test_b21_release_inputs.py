import hashlib
import importlib.util
from itertools import product
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'mechanical/physics/run_b21_checks.py'
module_spec = importlib.util.spec_from_file_location('run_b21_checks', SCRIPT)
checker = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(checker)


@pytest.fixture
def bundle(tmp_path):
    assembly = tmp_path / 'assembly.FCStd'
    assembly.write_bytes(b'assembly v1')
    export = tmp_path / 'cad'
    mesh = export / 'world/Frame.stl'
    mesh.parent.mkdir(parents=True)
    mesh.write_bytes(b'mesh v1')
    layout = {'source_sha256': hashlib.sha256(assembly.read_bytes()).hexdigest(),
              'world_motion': {'Frame': 'fixed'},
              'world_sha256': {'Frame': hashlib.sha256(mesh.read_bytes()).hexdigest()}}
    (export / 'cad_parts.json').write_text(json.dumps(layout))
    inputs = [tmp_path / name for name in ('hardware.json', 'spec.json', 'baseline.json', 'bom.csv')]
    for path in inputs:
        path.write_text('{}')
    return [assembly, export, *inputs], mesh


def test_same_layout_cannot_hide_a_changed_world_mesh(bundle):
    paths, mesh = bundle
    assert checker.inputs(*paths)['world_meshes_sha256']['Frame']
    mesh.write_bytes(b'mesh v2')
    with pytest.raises(ValueError, match='contents do not match'):
        checker.inputs(*paths)


def test_export_from_a_previous_cad_revision_is_refused(bundle):
    paths, _ = bundle
    paths[0].write_bytes(b'assembly v2')
    with pytest.raises(ValueError, match='does not match'):
        checker.inputs(*paths)


@pytest.mark.parametrize('extra', [False, True])
def test_partial_or_stale_export_mesh_set_is_refused(bundle, extra):
    paths, mesh = bundle
    if extra:
        mesh.with_name('PreviousPart.stl').write_bytes(b'previous export')
    else:
        mesh.unlink()
    with pytest.raises(ValueError, match='World meshes missing'):
        checker.inputs(*paths)


@pytest.mark.parametrize(('elastic_opening', 'status'), [(0.5, 'pass'), (0.9, 'fail')])
def test_stop_deflection_stays_within_tested_wire_clearance(elastic_opening, status):
    impact_cases = [{'modulus_MPa': modulus, 'opening_with_static_face_tolerance_and_impact_deg': 10.2 + elastic_opening}
                    for modulus in (500., 1000., 1800.)]
    stop = {'cad_sha256': 'cad', 'software_open_deg': 8., 'contact_trials': [
        {'face_shift_mm': shift, 'first_contact_deg': angle}
        for shift, angle in ((-.2, 9.05), (0., 9.6), (.2, 10.2))],
        'compound_contact_trials': [{'rigid_translation_mm': offset, 'first_contact_deg': 9.6}
                                    for offset in product((-.2, 0., .2), repeat=3)],
        'local_FE': {'meshes': [{'mesh_mm': size, 'impact_cases': impact_cases} for size in (.4, .5, .7)]}}
    wiring = {'cad_sha256': 'cad', 'clearance_bands': [{'up_to_deg': 10.25}, {'up_to_deg': 11.}],
              'poses': [{'fixed_pose': [i, 0, 0, 0, 0], 'contacts': []} for i in range(39)]}
    assert checker.jaw_envelope(stop, wiring, 'cad')['status'] == status
