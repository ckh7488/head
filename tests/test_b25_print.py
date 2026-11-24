"""Keep the B25 print project tied to the checked CAD and plate layout."""

from hashlib import sha256
import json
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


B25 = Path(__file__).resolve().parents[1] / 'mechanical/revisions/b25'


def metadata(element):
    return {entry.attrib['key']: entry.attrib['value'] for entry in element.findall('metadata[@key]')}


def test_b25_print_matches_current_cad_and_slice_record():
    design = json.loads((B25 / 'design.json').read_text())
    slices = json.loads((B25 / 'print-hf.json').read_text())
    shell = json.loads((B25 / 'front-shell-sync.json').read_text())
    project = B25 / 'R5-B25-P2S.3mf'
    assert sha256(project.read_bytes()).hexdigest() == design['p2s_sha256'] == slices['project_sha256']
    cad = B25 / 'R5-B25-Assembly.FCStd'
    assert sha256(cad.read_bytes()).hexdigest() == design['cad_sha256'] == slices['cad_sha256'] == shell['cad_sha256']

    with ZipFile(project) as archive:
        assert sha256(archive.read(shell['print_member'])).hexdigest() == shell['print_mesh_sha256']
        assert sha256(archive.read('Metadata/project_settings.config')).hexdigest() == slices['profile_sha256']
        config = ElementTree.fromstring(archive.read('Metadata/model_settings.config'))

    names = {entry.attrib['id']: metadata(entry)['name'] for entry in config.findall('object')}
    plates = {int(metadata(plate)['plater_id']): [names[metadata(instance)['object_id']]
              for instance in plate.findall('model_instance')] for plate in config.findall('plate')}
    assert sorted(plates) == list(range(1, 19))
    assert sum(map(len, plates.values())) == 57
    for item in slices['layout_checks']['standalone_parts_below_10_mm2']:
        assert plates[item['plate']] == [item['part']]
