from pydantic import BaseModel

from peopleops_api.evidence_verifier import EvidenceVerification, PolicyEvidenceVerifier


class FakeVerifierModel:
    def __init__(self, result: EvidenceVerification):
        self.result = result
        self.calls = 0

    def parse(self, *, purpose: str, instructions: str, output_model: type[BaseModel]):
        self.calls += 1
        assert output_model is EvidenceVerification
        return self.result


def evidence(*, synthetic: bool = True, fragment: str = "Managers must approve leave."):
    return [
        {
            "document_id": "doc-1",
            "policy_version_id": "version-1",
            "chunk_id": "chunk-1",
            "version": "2",
            "fragment": fragment,
            "verified": True,
            "synthetic": synthetic,
        }
    ]


def test_semantic_verifier_returns_structured_supported_evidence_without_language_rules():
    model = FakeVerifierModel(
        EvidenceVerification(
            answerable=True,
            insufficient_evidence=False,
            citation_indexes=[0],
            reason="The fragment directly supports the approval requirement.",
        )
    )

    result = PolicyEvidenceVerifier(model).verify(
        question="¿Quién debe aprobar la licencia?",
        evidence=evidence(),
        language="es",
    )

    assert result.answerable is True
    assert result.insufficient_evidence is False
    assert result.citation_indexes == [0]
    assert model.calls == 1


def test_semantic_verifier_removes_citations_when_model_marks_evidence_insufficient():
    model = FakeVerifierModel(
        EvidenceVerification(
            answerable=False,
            insufficient_evidence=True,
            citation_indexes=[],
            reason="The fragment is related but does not support the claim.",
        )
    )
    result = PolicyEvidenceVerifier(model).verify(
        question="Is relocation reimbursed?",
        evidence=evidence(),
        language="en",
    )

    assert result.answerable is False
    assert result.insufficient_evidence is True
    assert result.citation_indexes == []
    assert model.calls == 1


def test_valid_negative_decision_is_not_retried():
    model = FakeVerifierModel(
        EvidenceVerification(
            answerable=False,
            insufficient_evidence=True,
            citation_indexes=[],
            reason="The evidence is related but does not support the claim.",
        )
    )
    PolicyEvidenceVerifier(model).verify(
        question="Is relocation reimbursed?", evidence=evidence(), language="en"
    )
    assert model.calls == 1


def test_contradictory_verifier_result_can_retry_once():
    class ContradictoryModel(FakeVerifierModel):
        def __init__(self):
            super().__init__(EvidenceVerification(
                answerable=False,
                insufficient_evidence=False,
                citation_indexes=[0],
                reason="The evidence directly supports the claim.",
            ))

        def parse(self, *, purpose, instructions, output_model):
            self.calls += 1
            if self.calls == 1:
                return self.result
            return EvidenceVerification(
                answerable=True,
                insufficient_evidence=False,
                citation_indexes=[0],
                reason="The evidence supports the claim.",
            )

    model = ContradictoryModel()
    result = PolicyEvidenceVerifier(model).verify(
        question="Who approves leave?", evidence=evidence(), language="en"
    )
    assert model.calls == 2
    assert result.answerable is True


def test_unmarked_content_never_crosses_external_semantic_boundary():
    model = FakeVerifierModel(
        EvidenceVerification(
            answerable=True,
            insufficient_evidence=False,
            citation_indexes=[0],
            reason="unused",
        )
    )

    result = PolicyEvidenceVerifier(model).verify(
        question="What does this policy require?",
        evidence=evidence(synthetic=False),
    )

    assert result.answerable is False
    assert result.insufficient_evidence is True
    assert result.citation_indexes == []
    assert result.semantic_verification_status == "NOT_PERFORMED"
    assert model.calls == 0
