import pytest
from pydantic import ValidationError

from benchmarks.models import Gate2Variant


def test_gate2_variant_coerces_singular_expected_dimension_to_list():
    v = Gate2Variant(
        kind="incorrect_final_answer",
        final_output="wrong answer",
        expected_passed=False,
        expected_dimension="functional_correctness",
    )
    assert v.expected_dimensions == ["functional_correctness"]
    assert not hasattr(v, "expected_dimension")


def test_gate2_variant_accepts_plural_expected_dimensions_directly():
    v = Gate2Variant(
        kind="rubric_item_ignored",
        final_output="incomplete answer",
        expected_passed=False,
        expected_dimensions=["intent_satisfaction", "functional_correctness"],
    )
    assert v.expected_dimensions == ["intent_satisfaction", "functional_correctness"]


def test_gate2_variant_plural_field_takes_precedence_if_both_given():
    v = Gate2Variant(
        kind="incorrect_final_answer",
        final_output="wrong answer",
        expected_passed=False,
        expected_dimension="safety_and_rai",
        expected_dimensions=["functional_correctness"],
    )
    assert v.expected_dimensions == ["functional_correctness"]


def test_gate2_variant_fault_requires_nonempty_expected_dimensions():
    with pytest.raises(ValidationError):
        Gate2Variant(
            kind="incorrect_final_answer", final_output="wrong answer",
            expected_passed=False, expected_dimensions=[],
        )


def test_gate2_variant_paraphrase_rejects_expected_dimensions():
    with pytest.raises(ValidationError):
        Gate2Variant(
            kind="paraphrased_but_correct_final_answer", final_output="reworded but correct",
            expected_passed=True, expected_dimensions=["functional_correctness"],
        )


def test_gate2_variant_paraphrase_allows_empty_expected_dimensions():
    v = Gate2Variant(
        kind="paraphrased_but_correct_final_answer", final_output="reworded but correct",
        expected_passed=True,
    )
    assert v.expected_dimensions == []
