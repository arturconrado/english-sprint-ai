from english_sprint_api.pedagogy.eval_harness import load_cases, run_offline


def test_authorized_eval_harness_covers_forty_cases_and_invariants() -> None:
    cases = load_cases()
    result = run_offline()

    assert len(cases) == 40
    assert result == {"cases": 40, "selected": 20, "rejected": 20}
