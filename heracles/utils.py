import inspect
from typing import Any, Iterable, Type, Union as TypeUnion


def is_strict_subclass(typ: Type, classinfo: Type) -> bool:
    return typ is not classinfo and issubclass(typ, classinfo)


def get_as_type(t: TypeUnion[Type, Any]) -> Type:
    return t if inspect.isclass(t) else type(t)


def get_as_value(v):
    # TODO: Get rid of this
    return v() if inspect.isclass(v) else v


def get_type_name(t: TypeUnion[Type, Any]) -> str:
    return get_as_type(t).__name__


def padto(data: bytes, size: int, pad_val: bytes = b'\x00', leftpad: bool = False) -> bytes:
    assert isinstance(pad_val, bytes) and len(pad_val) == 1, 'Padding value must be 1 byte'
    if len(data) < size:
        padding = pad_val * (size - len(data))

        if not leftpad:
            data += padding
        else:
            data = padding + data
    return data


def value_or_default(value: Any, default: Any) -> Any:
    return value if value is not None else default


def first(it: Iterable) -> Any:
    return next(iter(it))


def last(it: Iterable) -> Any:
    return next(reversed(it))


def iter_chunks(it, size: int):
    for i in range(0, len(it), size):
        yield it[i:i+size]
