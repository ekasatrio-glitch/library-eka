from app.rag.citation import Citation, build_citations, extract_cited_ns, mark_cited
from app.rag.retriever import Hit


def _hit(i: int) -> Hit:
    return Hit(
        chunk_id=i,
        doc_id=i,
        title=f"Paper {i}",
        path=f"/tmp/{i}.pdf",
        page_start=i,
        page_end=i,
        year=2020,
        authors="A",
        text="x",
        distance=0.1,
    )


def _citations(n: int):
    return build_citations([_hit(i) for i in range(1, n + 1)])


# --- extract_cited_ns ---

def test_extract_square_single_and_multiple():
    assert extract_cited_ns("klaim [3]. lain [6].", style="square") == {3, 6}


def test_extract_square_comma_list_and_range():
    assert extract_cited_ns("a [1, 2] b [4-6]", style="square") == {1, 2, 4, 5, 6}


def test_extract_square_ignores_paren():
    assert extract_cited_ns("hasil (3) tanpa kurung siku", style="square") == set()


def test_extract_paren_single_and_list():
    assert extract_cited_ns("klaim (1). lain (2,3).", style="paren") == {1, 2, 3}


def test_extract_no_markers():
    assert extract_cited_ns("tanpa sitasi sama sekali", style="square") == set()


# --- mark_cited ---

def test_mark_cited_flags_subset():
    cits = _citations(6)
    mark_cited(cits, {3, 6})
    assert [c.cited for c in cits] == [False, False, True, False, False, True]


def test_mark_cited_ignores_out_of_range():
    cits = _citations(3)
    mark_cited(cits, {2, 9, 2020})  # 9 and 2020 out of range
    assert [c.cited for c in cits] == [False, True, False]


def test_mark_cited_empty_set_keeps_all_cited():
    cits = _citations(3)
    mark_cited(cits, set())
    assert all(c.cited for c in cits)


def test_mark_cited_all_out_of_range_keeps_all_cited():
    cits = _citations(3)
    mark_cited(cits, {2020})
    assert all(c.cited for c in cits)


def test_citation_to_dict_has_cited():
    cits = _citations(1)
    assert cits[0].to_dict()["cited"] is True
