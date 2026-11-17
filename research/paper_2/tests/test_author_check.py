import json

from research.paper_2 import author_check as AC


def test_page_carries_only_numbers_and_text_never_keys():
    items = [{"n": 1, "key": "abc123|D5|en|-", "text": "Impression: lesions </script> here"},
             {"n": 2, "key": "def456|D1|en|-", "text": "Normal study."}]
    page = AC.render(items)
    assert "abc123" not in page and "|D5|" not in page and "D1|" not in page
    data = page.split('<script id="data" type="application/json">')[1].split("</script>")[0]
    assert json.loads(data.replace("<\\/", "</")) == [{"n": 1, "text": "Impression: lesions </script> here"},
                                                     {"n": 2, "text": "Normal study."}]
    assert "__" not in page.replace("__N__", "")  # every placeholder filled


def test_score_folds_the_three_choices_into_the_two_judge_questions():
    mapping = {"1": "k1", "2": "k2", "3": "k3", "4": "k4"}
    rows = {"k1": {"ms": False, "unq": False}, "k2": {"ms": True, "unq": False},
            "k3": {"ms": True, "unq": True}, "k4": {"ms": True, "unq": True}}
    labels = {"1": 1, "2": 2, "3": 3, "4": 2}
    res = AC.score(labels, mapping, rows)
    assert res["ms_suggestive"]["tp"] == 3 and res["ms_suggestive"]["tn"] == 1
    assert res["unqualified_ms_suggestive"]["tp"] == 1 and res["unqualified_ms_suggestive"]["fp"] == 1
    assert res["author_counts"] == {"not_ms": 1, "qualified": 2, "unqualified": 1}


def test_score_refuses_an_unfinished_check():
    import pytest
    with pytest.raises(SystemExit):
        AC.score({"1": 1}, {"1": "k1", "2": "k2"}, {"k1": {"ms": False, "unq": False}, "k2": {"ms": True, "unq": True}})
