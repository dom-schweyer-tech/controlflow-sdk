import pandas as pd

from controlflow_sdk.model.population import ColumnMeta, Population
from controlflow_sdk.pipeline.compile import compile_pipeline_procedures
from controlflow_sdk.pipeline.model import parse_pipeline


def _multi_check_one_procedure() -> dict:
    # ONE procedure (p1) owning TWO checks (t1, t2) over the same filtered trunk.
    return {
        "nodes": [
            {"id": "imp", "type": "import", "source_id": "je"},
            {"id": "flt", "type": "filter", "inputs": ["imp"], "config": {
                "logic": "all", "conditions": [{"column": "kind", "op": "eq", "value": "manual"}]}},
            {"id": "t1", "type": "test", "inputs": ["flt"], "title": "preparer=approver",
             "config": {"logic": "all", "item_key_column": "je_id", "procedure_id": "p1",
                        "conditions": [{"column": "preparer", "op": "eq", "value": "approver"}]}},
            {"id": "t2", "type": "test", "inputs": ["flt"], "title": "no approval",
             "config": {"logic": "all", "item_key_column": "je_id", "procedure_id": "p1",
                        "conditions": [{"column": "approval", "op": "is_empty"}]}},
        ],
        "procedures": [
            {"id": "p1", "code": "P1", "name": "Manual JE Review",
             "assertion": "Segregation of Duties", "position": 0},
        ],
    }


def test_one_compiled_procedure_carries_metadata():
    p = parse_pipeline(_multi_check_one_procedure())
    procs = compile_pipeline_procedures(p)
    assert len(procs) == 1
    assert procs[0].procedure_id == "p1"
    assert procs[0].code == "P1"
    assert procs[0].title == "Manual JE Review"
    assert procs[0].assertion == "Segregation of Duties"


def test_compiled_union_matches_interpreter(tmp_path):
    """The generated union test() must equal the union of the interpreter over the
    procedure's checks (learning 0009)."""
    p = parse_pipeline(_multi_check_one_procedure())
    procs = compile_pipeline_procedures(p)
    result = procs[0].result  # CompileResult: union test() string for the 2 checks

    df = pd.DataFrame([
        {"je_id": "A", "kind": "manual", "preparer": "approver", "approval": ""},   # fails both
        {"je_id": "B", "kind": "manual", "preparer": "alice", "approval": ""},       # fails t2
        {"je_id": "C", "kind": "manual", "preparer": "approver", "approval": "yes"}, # fails t1
        {"je_id": "D", "kind": "auto",   "preparer": "approver", "approval": ""},    # filtered out
    ])
    pop = Population(
        df=df,
        columns=[ColumnMeta(original_name="je_id", display_name="je_id", is_key=True)],
        source_id="je",
    )

    ns: dict = {}
    exec(result.test_code, ns)  # noqa: S102 — generated, guardrailed
    generated = ns["test"](pop, {})
    keys = sorted(v["item_key"] for v in generated)
    # A (both), B (t2), C (t1) ⇒ keys A,A,B,C before dedupe (concat of both checks)
    assert keys == ["A", "A", "B", "C"]
