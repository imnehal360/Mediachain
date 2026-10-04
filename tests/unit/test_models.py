import pytest
from pydantic import ValidationError

from mediachain.core.config import ProcessingConfig
from mediachain.core.models import Document, Interval, Modality, stable_id


@pytest.mark.parametrize(
    "start,end", [(2, 1), (-1, 1), (None, 1), (0, float("inf")), (float("nan"), 2)]
)
def test_invalid_intervals(start, end):
    with pytest.raises(ValidationError):
        Interval(start_time=start, end_time=end)


def test_document_roundtrip_and_reference():
    d = Document(
        id="d",
        content="hello",
        asset_id="a",
        source="a.mp4",
        modality=Modality.AUDIO,
        start_time=1.2,
        end_time=3,
    )
    assert Document.model_validate_json(d.model_dump_json()) == d
    assert d.reference().start_time == 1.2
    assert d.reference().media_id == "a"
    assert stable_id({"a": 1, "b": 2}) == stable_id({"b": 2, "a": 1})


def test_chunk_config():
    with pytest.raises(ValidationError):
        ProcessingConfig(chunk_size=10, chunk_overlap=10)
