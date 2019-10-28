import copy
import inspect
import itertools
from typing import Any, Iterable, Iterator, Mapping, Optional, Sequence, Type, Union as TypeUnion


ParameterKind = type(inspect.Parameter.KEYWORD_ONLY)


def is_type(v: Any) -> bool:
    return inspect.isclass(v)


def as_type(t: Any) -> Type:
    return t if is_type(t) else type(t)


def get_as_value(v: Any) -> Any:
    # TODO: Get rid of this
    return v() if inspect.isclass(v) else v


def type_name(t: Any) -> str:
    try:
        return t.__name__
    except AttributeError:
        return type(t).__name__


def padto(data: bytes, size: int, pad_val: bytes = b'\x00', leftpad: bool = False) -> bytes:
    assert isinstance(pad_val, bytes) and len(pad_val) == 1, 'Padding value must be 1 byte'
    if len(data) < size:
        padding = pad_val * (size - len(data))

        if not leftpad:
            data += padding
        else:
            data = padding + data
    return data


def func_params(func, kind: Optional[ParameterKind] = None) -> tuple:
    return tuple(
        p for p in inspect.signature(func).parameters.values()
        if kind is None or p.kind == kind)


def value_or_default(value: Any, default: Any) -> Any:
    return value if value is not None else default


def first(it: Iterable) -> Any:
    return next(iter(it))


def last(it: Iterable) -> Any:
    return next(reversed(it))


def iter_chunks(seq: Sequence, size: int) -> Iterator:
    return (seq[i:i+size] for i in range(0, len(seq), size))


def is_strict_subclass(cls: Type, classinfo: Type) -> bool:
    return issubclass(cls, classinfo) and cls is not classinfo


def is_classdef_in_classdict(classdict: Mapping[str, Any], name: str, value: Type):
    # Try to identify the case of a Serializer defined in the body of
    # the struct and ignore it, unless the user specifically chose to
    # redefine it as a member, such as the following case:
    # class Foo(Struct):
    #     class Bar(Struct):
    #         pass
    #     Bar = Bar  # Treated as member
    # Make sure to only ignore if this is a new class definition by
    # comparing to the existing value, if any.
    if inspect.isclass(value) and name == type_name(value) and value != classdict.get(name):
        if getattr(value, '__module__', None) == classdict.get('__module__'):
            class_qual = getattr(value, '__qualname__', '').rsplit('.', 1)[0]
            if classdict.get('__qualname__') == class_qual:
                return True
    return False


def as_iter(maybe_iter: Any) -> Iterator:
    try:
        return iter(maybe_iter if maybe_iter is not None else ())
    except TypeError:
        return iter((maybe_iter,))


def chain(value: Any, rest: Optional[Any] = None) -> Iterator:
    return itertools.chain(as_iter(value), as_iter(rest))


def is_immutable(value: Any) -> bool:
    if isinstance(value, (tuple, frozenset)):
        return all(map(is_immutable, value))
    elif isinstance(value, (str, bytes, range, memoryview, bool, int, float, complex)):
        return True
    else:
        return False


def copy_if_mutable(value: Any) -> Any:
    """ Returns a copy of a value if mutable, otherwise returns the original value """
    return copy.deepcopy(value) if not is_immutable(value) else value
