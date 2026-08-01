import pytest
from ai_governance_api.domain.evidence import (
    InvalidEvidenceName,
    UnsupportedEvidenceType,
    normalize_filename,
    validate_content,
)


def test_filename_is_reduced_to_display_only_basename() -> None:
    assert normalize_filename("../../reports/security.pdf") == "security.pdf"
    assert normalize_filename(r"C:\fakepath\security.pdf") == "security.pdf"

    with pytest.raises(InvalidEvidenceName):
        normalize_filename("bad\x00name.pdf")
    with pytest.raises(InvalidEvidenceName):
        normalize_filename("invoice\u202egnp.pdf")


@pytest.mark.parametrize(
    ("filename", "content_type", "content"),
    [
        ("report.pdf", "application/pdf", b"not-a-pdf"),
        ("report.txt", "application/pdf", b"%PDF-1.7"),
        ("report.json", "application/json", b"{invalid}"),
        ("report.txt", "text/plain", b"binary\x00content"),
    ],
)
def test_content_validation_rejects_spoofed_or_invalid_files(
    filename: str,
    content_type: str,
    content: bytes,
) -> None:
    with pytest.raises(UnsupportedEvidenceType):
        validate_content(filename=filename, content_type=content_type, content=content)
