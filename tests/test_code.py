import pytest

from elune import Code, decode, encode
from elune.code import Code as SubmoduleCode


def test_string_inheritance():
    assert Code is SubmoduleCode
    assert issubclass(Code, str)
    code = Code("return x", {"x": 1})
    assert isinstance(code, str)
    assert str(code) == "return x"
    assert code.upper() == "RETURN X"
    assert code[:6] == "return"
    assert len(code) == 8
    assert code + ";" == "return x;"
    assert code.startswith("return")
    assert code != "return x"
    with pytest.raises(TypeError):
        hash(code)


def test_wire_types_and_subclasses():
    class CustomCode(Code):
        pass

    for cls in (Code, CustomCode):
        for scope in (None, {}, {"x": 1}):
            code = cls("return x", scope)
            assert isinstance(code, cls)
            data = encode({"x": code})
            assert data[4] == (0x0D if scope is None else 0x0F)
            result = decode(data)["x"]
            assert type(result) is Code
            assert isinstance(result, str)
            assert result == code
            assert result.scope == scope
            assert encode({"x": result}) == data


def test_copy_preserves_live_scope():
    scope = {"x": 1}
    original = Code("x", scope)
    copied = Code(original, y=2)
    assert original.scope is scope
    assert copied.scope is scope
    assert scope == {"x": 1, "y": 2}
