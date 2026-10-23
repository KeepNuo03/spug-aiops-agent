"""Cross-check a diagnosis against the evidence it claims to rest on.

The prompt tells the model to stay within the evidence, but instructions are not a guarantee. A
named process that appears nowhere in the collected output is the clearest sign of invention, and
it is cheap to check in code. A failed check does not discard the answer — the report is still
useful — but the confidence drops to zero and the reason is recorded.
"""

from diagnosis.models import Diagnosis, VerifiedDiagnosis


def verify(diagnosis: Diagnosis, evidence_blob: str, known_probes: list[str]) -> VerifiedDiagnosis:
    data = diagnosis.model_dump()
    problems = []

    culprit = diagnosis.culprit_process
    if culprit and culprit.name.lower() not in evidence_blob.lower():
        problems.append(f"process '{culprit.name}' does not appear in the collected evidence")

    if culprit and culprit.pid is not None and str(culprit.pid) not in evidence_blob:
        problems.append(f"pid {culprit.pid} does not appear in the collected evidence")

    unknown_probes = [p for p in diagnosis.evidence_used if p not in known_probes]
    if unknown_probes:
        problems.append(f"cites probes that were not run: {', '.join(unknown_probes)}")

    if problems:
        data["confidence"] = 0.0
    return VerifiedDiagnosis(**data, verified=not problems, verification_note="; ".join(problems) or None)
