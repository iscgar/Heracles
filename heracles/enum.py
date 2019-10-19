import sys
import typing
import collections

from .base import Serializer, SerializerMeta, SerializerMetadata, MetaDict
from .scalars import *
from .utils import first, last, is_strict_subclass, get_type_name, get_as_type

__all__ = ['Enum', 'Literal']


class Literal(object):
    pass


class EnumMeta(SerializerMeta):
    def __new__(cls, name: str, bases: typing.Sequence, classdict: typing.Dict[str, typing.Any]):
        if classdict.get('__module__') != __name__ and not classdict.get(SerializerMeta.METAATTR):
            enum_base = None

            for base in bases:
                if not is_strict_subclass(base, Serializer):
                    continue

                if getattr(sys.modules[__name__], get_type_name(base), None) != base:
                    raise TypeError('enum classes can only derive directly from Enum')

                enum_base = base

            classdict.update({
                SerializerMeta.METAATTR: SerializerMetadata(
                    literals=classdict.members, **{k: v for k, v in enum_base.metadata().items()}),
            })

        return super().__new__(
            cls, name, bases, collections.OrderedDict(classdict))

    def __prepare__(name: str, bases: typing.Sequence, **kwargs) -> MetaDict:
        def on_literal_add(members, name, value):
            if value is not None and not issubclass(get_as_type(value), (int, Literal)):
                return None

            if value is None or issubclass(get_as_type(value), Literal):
                return 0 if not members else last(members.values()) + 1

            return value

        return MetaDict(name, on_literal_add)

    def __call__(cls, *args, **kwargs):
        if cls is Enum:
            if not kwargs:
                if len(args) == 1 and is_strict_subclass(args[0], Scalar):
                    underlying = args[0]
                    VALID_UNDERLYING_TYPES = (
                        u8, u16, u32, u64, i8, i16, i32, i64,
                        u8_le, u16_le, u32_le, u64_le, i8_le, i16_le, i32_le, i64_le,
                        u8_be, u16_be, u32_be, u64_be, i8_be, i16_be, i32_be, i64_be)

                    if underlying not in VALID_UNDERLYING_TYPES:
                        raise TypeError('Invalid underlying type for Enum')

                    name = f'Enum({get_type_name(underlying)})'
                    typ = getattr(sys.modules[__name__], name, None)

                    if typ is None:
                        serializer = underlying()
                        typ = type(name, (Enum,), {
                            SerializerMeta.METAATTR: SerializerMetadata(len(serializer)),
                            'serializer': serializer})
                        setattr(sys.modules[__name__], name, typ)
                    
                    return typ

        return super().__call__(*args, **kwargs)

    def __setattr__(cls, name: str, value: typing.Any) -> None:
        if name in cls.literals():
            raise AttributeError(f'{get_type_name(cls)}: cannot reassign Enum literal')
        super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if name in cls.literals():
            raise AttributeError(f'{get_type_name(cls)}: cannot delete Enum literal')
        super().__delattr__(name)

    def __repr__(cls) -> str:
        return f'<enum {get_type_name(cls)}>'


class Enum(Serializer, metaclass=EnumMeta):
    def __init__(self, value=None, *args, **kwargs):
        if value is None:
            if self.literals():
                value = first(self.literals().values())
            else:
                value = 0

        super().__init__(value, *args, **kwargs)

    @classmethod
    def literals(cls) -> typing.Mapping[str, int]:
        return cls.metadata().literals

    def validate(self, value: typing.Optional[typing.Union['Enum', int]]=None) -> int:
        value = self.serializer.validate(value)
        # TODO: flags
        if value not in self.literals().values():
            raise ValueError('value is not one of the enum literals')
        return value

    def serialize_value(self, value: typing.Optional[typing.Union['Enum', int]], settings: typing.Dict[str, typing.Any]=None) -> bytes:
        return self.serializer.serialize_value(value, settings)

    def deserialize(self, raw_data: typing.ByteString, settings: typing.Dict[str, typing.Any]=None) -> int:
        return self.serializer.deserialize(raw_data, settings)

    def get_literal_name(self, literal: int) -> str:
        # TODO: flags
        return first(k for k, v in self.literals().items() if v == literal)
    
    def render(self, value: typing.Optional[typing.Union['Enum', int]]=None) -> str:
        value = self.get_serializer_value(value)
        self.validate(value)
        return f'{get_type_name(self)}.{self.get_literal_name(value)} ({value})'

    def compare(self, other: typing.Union['Enum', int], value: typing.Optional[typing.Union['Enum', int]]=None) -> bool:
        return self.serializer.compare(other, value)

    def __int__(self) -> int:
        return self.value

    def __iter__(self) -> typing.ValuesView:
        return self.literals().values()


Enum = Enum(i32)