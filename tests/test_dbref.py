import copy
import gc

import pytest

import bson
from bson.dbref import DBRef

try:
    import _p_bson as reference
    from _p_bson.dbref import DBRef as ReferenceDBRef
except ImportError:
    reference = None


def test_api():
    ref = DBRef("items", 42, "db", {"x": 2}, x=1, y=3)
    assert (ref.collection, ref.id, ref.database) == ("items", 42, "db")
    assert (ref.x, ref.y) == (2, 3)
    assert list(ref.as_doc()) == [
        "$" + "ref",
        "$" + "id",
        "$" + "db",
        "x",
        "y",
    ]
    assert repr(ref) == "DBRef('items', 42, 'db', x=2, y=3)"
    assert ref == DBRef("items", 42, "db", x=2, y=3)
    assert ref != DBRef("items", 43, "db", x=2, y=3)
    assert ref != ref.as_doc()
    assert hash(ref) == hash(DBRef("items", 42, "db", y=3, x=2))
    with pytest.raises(AttributeError):
        ref.missing  # ruff: ignore[useless-expression]
    with pytest.raises(AttributeError):
        ref.collection = "other"  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(TypeError):
        hash(DBRef("items", []))


def test_validation():
    for collection, database in ((1, None), (None, None), ("c", 2)):
        with pytest.raises(TypeError):
            DBRef(collection, 1, database)  # pyright: ignore[reportArgumentType]
    assert DBRef("", None, "").database == ""  # ruff: ignore[compare-to-empty-string]


def test_nested_and_root_recognition():
    for doc in (
        {"$" + "ref": "c", "$" + "id": None},
        {"$" + "id": 1, "$" + "ref": "c", "extra": [1, 2]},
        {"$" + "ref": "c", "$" + "id": 2, "$" + "db": None},
    ):
        assert bson.decode(bson.encode(doc)) == doc
        assert isinstance(
            bson.decode(bson.encode({"x": [doc]}))["x"][0], DBRef,
        )
    for doc in (
        {"$" + "ref": "c"},
        {"$" + "ref": 1, "$" + "id": 2},
        {"$" + "ref": "c", "$" + "id": 2, "$" + "db": 3},
    ):
        assert bson.decode(bson.encode({"x": doc})) == {"x": doc}


def test_roundtrip_and_check_keys():
    ref = DBRef("c", {"$" + "bad": [1]}, "db", _extra={"$" + "x": 1, "a.b": 2})
    wire = bson.encode({"x": ref, "after": 1}, check_keys=True)
    assert bson.decode(wire) == {"x": ref, "after": 1}
    assert bson.decode_all(wire * 3) == [{"x": ref, "after": 1}] * 3
    with pytest.raises(bson.InvalidDocument):
        bson.encode({"x": ref, "$" + "bad": 1}, check_keys=True)
    with pytest.raises(bson.InvalidDocument):
        bson.encode({"x": DBRef("c", 1, _extra={"bad\0": 1})})


def test_cycles_and_gc():
    identifier = {}
    ref = DBRef("c", identifier)  # pyright: ignore[reportUnknownArgumentType]
    identifier["ref"] = ref
    with pytest.raises(bson.InvalidDocument):
        bson.encode({"x": ref})
    assert gc.is_tracked(ref)


def test_deepcopy():
    ref = DBRef("c", [1], metadata={"x": []})
    other = copy.deepcopy(ref)
    assert ref == other
    assert ref.id is not other.id
    assert ref.metadata is not other.metadata


@pytest.mark.skipif(
    reference is None, reason="PyMongo reference is not installed",
)
def test_pymongo_differential():
    for identifier in (None, 1, "id", {"": [1, 2]}):
        for database in (None, "", "db"):
            actual = DBRef("c", identifier, database, x=2)
            expected = ReferenceDBRef("c", identifier, database, x=2)
            assert repr(actual) == repr(expected)
            for check in (False, True):
                wire = bson.encode({"x": actual}, check_keys=check)
                assert wire == reference.encode(  # pyright: ignore[reportOptionalMemberAccess]
                    {"x": expected}, check_keys=check,
                )
                assert bson.decode(wire)["x"] == actual
                assert reference.decode(wire)["x"] == expected  # pyright: ignore[reportUnknownMemberType, reportOptionalMemberAccess]
