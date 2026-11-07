"""Deterministic claim-extraction dataset (tests/data/claim_dataset.json): splitting, spans, features."""
import json
from pathlib import Path

import pytest

from vericode.claims import extract_claims

DATA = json.loads((Path(__file__).parent / "data" / "claim_dataset.json").read_text())


def _get(c, key):
    obj = c.to_dict()
    for part in key.split("."):
        obj = obj[part]
    return obj


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["id"] for c in DATA["cases"]])
def test_claim_dataset(case):
    claims = extract_claims(case["text"])
    got = [c.claim for c in claims]
    assert got == [e["claim"] for e in case["claims"]], got
    for c, exp in zip(claims, case["claims"]):
        # spans are exact: sentence span always, fragment span whenever the claim text is verbatim
        assert case["text"][c.span[0]:c.span[1]] == c.source_text
        if c.fragment_span:
            frag = case["text"][c.fragment_span[0]:c.fragment_span[1]]
            assert frag[1:] == c.claim.rstrip(".")[1:] and frag[0].lower() == c.claim[0].lower()  # only clause capitalisation may differ
        else:
            assert c.derived
        for k, v in exp.items():
            if k == "claim":
                continue
            assert _get(c, k) == v, (c.claim, k, _get(c, k))


def test_incomplete_claims_are_never_verified(tmp_path):
    from vericode import stale
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"sources": [{"title": "CNCF", "url": "https://www.cncf.io/projects/kubernetes/", "keywords": ["maintained", "cncf", "now"],
                                          "min_match": 1, "content": "It is now maintained by the CNCF."}]}))
    s = stale.FixtureSearch(p)
    r = stale.analyze("Kubernetes was originally designed at Google. It is now maintained by the CNCF.", search=s)
    inc = r["claims"][1]
    assert inc["status"] == "UNVERIFIED" and inc["missing_evidence"] == "claim subject is unresolved" and inc["evidence"] == []
