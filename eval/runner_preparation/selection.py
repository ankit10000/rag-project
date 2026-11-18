"""Explicit scoring interfaces for development; the default remains frozen v1."""


def select_scorer(scorer_version='v1', *, development=False, annotations=None):
    """Return the original five-argument v1 scorer unless v2.1 is explicit.

    v2.1 requires ``development=True`` and a caller-supplied annotation set.
    File-level annotation validation is the responsibility of a dataset-aware
    caller (the offline wrapper performs it); the bound adapter enforces the
    scoring module's per-case checks. This is not an acceptance-scorer selector.
    """
    if scorer_version == 'v1':
        from eval.phase35.run_eval import score_generic
        return score_generic
    if scorer_version != '2.1.0':
        raise ValueError('unknown scorer version; expected v1 or explicit 2.1.0')
    if development is not True:
        raise ValueError('scorer 2.1.0 is development-only; adoption is pending')
    if not isinstance(annotations, dict) or not isinstance(annotations.get('cases'), dict):
        raise ValueError('explicit caller-supplied annotations are required for v2.1')
    import re
    if (not isinstance(annotations.get('dataset_version'), str) or not annotations['dataset_version']
            or not isinstance(annotations.get('dataset_sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', annotations['dataset_sha256'])
            or any(not isinstance(cid, str) or not cid for cid in annotations['cases'])):
        raise ValueError('complete annotation identity is required')
    from eval.scoring_v2 import bind_v1_signature, load_annotations
    parsed = load_annotations(annotations)
    return bind_v1_signature(parsed)
