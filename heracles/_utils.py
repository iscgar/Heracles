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


def is_class_in_class_body(classdict, name, value):
    # Try to identify the case of a Serializer defined in the body of
    # the struct and ignore it, unless the user specifically chose to
    # redefine it as a member, such as the following case:
    # class Foo(Struct):
    #     class Bar(Struct):
    #         pass
    #     Bar = Bar  # Treated as member
    # Make sure to only ignore if this is a new class definition by
    # comparing to the existing value, if any.
    if inspect.isclass(value) and name == get_type_name(value) and value != classdict.get(name):
        if getattr(value, '__module__', None) == classdict.get('__module__'):
            class_qual = getattr(value, '__qualname__', '').rsplit('.', 1)[0]
            if classdict.get('__qualname__') == class_qual:
                return True
    return False


class instanceoverride(object):
    def __init__(self, method, instance=None, owner=None):
        self.method = method
        self.instance = instance
        self.owner = owner

    def __get__(self, instance, owner=None):
        return type(self)(self.method, instance, owner)

    def __call__(self, *args, **kwargs):
        return self.__func__(self.owner, *args, **kwargs)
    
    def __func__(self, owner, *args, **kwargs):
        instance = self.instance
        if instance is None:
            if not args or not issubclass(get_as_type(args[0]), self.owner):
                for base in self.owner.__mro__[1:]:
                    method = getattr(base, self.method.__name__)
                    if method is not None:
                        return method.__func__(owner, *args, **kwargs)
                if not args:
                    raise TypeError(f"{get_type_name(self.method)}() missing 1 required positional argument: 'self'")
            instance, args = args[0], args[1:]

        return self.method(instance, *args, **kwargs)
    
    def __repr__(self):
        binder = self.instance if self.instance is not None else self.owner
        if binder is not None:
            return f'<bound method {self.method.__qualname__} of {binder}>'
        else:
            return repr(self.method)
