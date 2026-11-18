"""Read-only verification and new-file-only candidate snapshots; never re-freezes."""
import json
from pathlib import Path
import subprocess
from eval.framework.integrity import dataset_hash
from eval.scoring_v2 import validate_annotations
from eval.scoring_v2.rescore import load_pinned_dataset
from .candidate import build_candidate,validate_candidate,_relative,canonical_bytes
import hashlib

CURRENT_ANNOTATION='eval/scoring_v2/annotations.json'
HISTORICAL_ANNOTATION='docs/remediation/phase_e2_engineering/wp8_evidence/flip_inputs/final/literal-annotations.c1bbcae.json'
HISTORICAL_REVISION='c1bbcae9a21e389c16c3f1587de5acc1b5209e37'


def strict_json(data):
    def pairs(items):
        out={}
        for key,value in items:
            if key in out:
                raise ValueError('duplicate JSON key')
            out[key]=value
        return out
    return json.loads(data,object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite JSON')))


def capture_inputs(root):
    """Capture the unchanged parent, WP6/WP7 snapshot and two separate bindings."""
    root=Path(root)
    parent=strict_json((root/'eval/phase35/frozen_manifest.json').read_bytes())
    if parent.get('content_sha256') != hashlib.sha256(canonical_bytes(parent.get('content'))).hexdigest():
        raise ValueError('parent frozen manifest content digest mismatch')
    paths={_relative(asset['path']) for asset in parent['content']['assets']}
    paths.update(p.relative_to(root).as_posix() for folder in ('eval/scoring_v2','eval/runner_preparation')
                 for p in (root/folder).glob('*.py'))
    paths.add(CURRENT_ANNOTATION)
    sources={path:(root/path).read_bytes() for path in sorted(paths)}
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip()
    annotation_inputs=[]
    for path,revision in ((CURRENT_ANNOTATION,head),(HISTORICAL_ANNOTATION,HISTORICAL_REVISION)):
        data=(root/path).read_bytes();ann=strict_json(data)
        docs,cases,pin=load_pinned_dataset(root,revision)
        errors=validate_annotations(ann,cases,docs)
        if errors:
            raise ValueError('annotation validation failed for '+path+': '+'; '.join(errors))
        annotation_inputs.append(dict(path=path,data=data,dataset_revision=pin['git_rev'],dataset_sha256=dataset_hash(cases)))
    return parent,sources,annotation_inputs,head


def build_current_candidate(root):
    parent,sources,annotations,head=capture_inputs(root)
    return build_candidate(parent,sources,annotations,source_head=head)


def validate_current_candidate(root,candidate):
    """Reread actual current files, independently validate annotations, then compare."""
    parent,sources,annotations,head=capture_inputs(root)
    return validate_candidate(candidate,parent,sources,annotations,source_head=head)


def write_candidate(root,output):
    """Create a separate proposal only; existing output paths are never replaced."""
    output=Path(output)
    root=Path(root)
    official=root/'eval/phase35'
    if output.resolve().is_relative_to(official.resolve()):
        raise ValueError('candidate must be separate from the official evaluation subtree')
    candidate=build_current_candidate(root)
    validate_current_candidate(root,candidate)
    with output.open('x',encoding='utf-8') as handle:
        json.dump(candidate,handle,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)
        handle.write('\n')
    return candidate
