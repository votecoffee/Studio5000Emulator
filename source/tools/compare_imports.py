"""Compare modeled content of two complete L5X exports without modifying either.

This is an offline conversion check, not a native round-trip or runtime proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logixlab.model import Project
from logixlab.runtime import Engine
from logixlab.server import serialize_nodes


def xml_shape(element):
    return {'tag': element.tag, 'attributes': dict(element.attrib),
            'text': (element.text or '').strip(),
            'children': [xml_shape(child) for child in element]}


def modeled_content(project):
    def routine(value):
        return {'kind': value.kind, 'problems': value.problems, 'lines': value.lines,
                'rungs': [{'number': rung['number'], 'nodes': serialize_nodes(rung['nodes']),
                           'comment': rung['comment'].strip()} for rung in value.rungs]}
    controller = ET.parse(project.path).getroot().find('Controller')
    return {
        'identity': {'name': project.name, 'processor': project.processor,
                     'major': project.version, 'minor': project.minor_version},
        'tags': {key: {field: getattr(tag, field) for field in
                      ('name', 'dtype', 'scope', 'alias', 'external_access', 'constant', 'tag_class', 'problem')}
                 for key, tag in project.tags.items()},
        'initial_values': project.initial,
        'programs': project.programs, 'tasks': project.tasks,
        'routines': {key: routine(value) for key, value in project.routines.items()},
        'data_types': {key: xml_shape(value) for key, value in project.udts.items()},
        'add_on_instructions': {key: {'parameters': value.parameters, 'locals': value.locals,
                                    'modes': value.modes, 'problems': value.problems,
                                    'routines': {k: routine(v) for k, v in value.routines.items()}}
                                for key, value in project.aois.items()},
        'modules': [xml_shape(value) for value in controller.findall('./Modules/Module')],
        'controller_settings': {key: value for key, value in controller.attrib.items()
                                if key not in ('Use', 'ProjectCreationDate', 'LastModifiedDate')},
    }


def compare_exports(reference, candidate):
    paths = [Path(reference), Path(candidate)]
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    projects = [Project(path) for path in paths]
    content = [modeled_content(project) for project in projects]
    groups = {key: content[0][key] == content[1][key] for key in content[0]}
    blockers = [Engine(project).blockers for project in projects]
    unchanged = all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in zip(paths, hashes))
    def counts(project):
        return {'tags': len(project.tags), 'routines': len(project.routines),
                'rungs': sum(len(routine.rungs) for routine in project.routines.values()),
                'data_types': len(project.udts), 'add_on_instructions': len(project.aois)}
    return {'reference_sha256': hashes[0], 'candidate_sha256': hashes[1],
            'groups_equal': groups, 'different_groups': [key for key, equal in groups.items() if not equal],
            'reference_counts': counts(projects[0]), 'candidate_counts': counts(projects[1]),
            'reference_blockers': blockers[0], 'candidate_blockers': blockers[1],
            'inputs_unchanged': unchanged,
            'modeled_content_matches': all(groups.values()) and not any(blockers) and unchanged,
            'native_round_trip': 'NOT VERIFIED', 'native_runtime_equivalence': 'NOT VERIFIED',
            'studio_go_online': 'NOT VERIFIED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, type=Path, help='Known native complete L5X export')
    parser.add_argument('--candidate', required=True, type=Path, help='Candidate complete L5X export')
    parser.add_argument('--out', required=True, type=Path, help='Private JSON comparison receipt')
    args = parser.parse_args()
    resolved = args.out.resolve()
    if (resolved in (args.reference.resolve(), args.candidate.resolve()) or
            args.out.exists() and any(args.out.samefile(path) for path in (args.reference, args.candidate))):
        parser.error('Output must not overwrite either input')
    result = compare_exports(args.reference, args.candidate)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['modeled_content_matches'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
