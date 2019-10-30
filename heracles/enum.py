import sys
import types
import collections
from typing import Any, ByteString, Dict, Iterator, Mapping, Optional, Sequence, Type, Union as TypeUnion

from .base import Serializer, SerializerMeta, SerializerMetadata, MetaDict, byte_size
from .scalars import *
from ._utils import first, last, type_name, as_type, get_as_value, func_params, ParameterKind, strictproperty

__all__ = ['Enum', 'auto']


class auto(object):
    pass


class EnumMetadata(SerializerMetadata):
    __slots__ = ('serializer', 'flags', 'members')
    _VALID_UNDERLYING_TYPES = (
        u8, u16, u32, u64, i8, i16, i32, i64,
        u8_le, u16_le, u32_le, u64_le, i8_le, i16_le, i32_le, i64_le,
        u8_be, u16_be, u32_be, u64_be, i8_be, i16_be, i32_be, i64_be)

    def __init__(self, *, members: collections.OrderedDict, underlying: Type[Scalar] = i32, flags: bool = False):
        if underlying not in self._VALID_UNDERLYING_TYPES:
            raise TypeError(f'Invalid underlying type for Enum: {type_name(underlying)}')
        serializer = get_as_value(underlying)
        try:
            for k, v in members.items():
                serializer._heracles_validate_(v)
        except ValueError as e:
            raise ValueError(f'Invalid value for literal {v}: {str(e)}')
        self.flags = flags
        self.serializer = serializer
        self.members = members
        super().__init__(byte_size(serializer))


class EnumMeta(SerializerMeta):
    _ENUM_ARGS = tuple(
        p.name for p in func_params(EnumMetadata.__init__, ParameterKind.KEYWORD_ONLY))

    def __new__(cls, name: str, bases: Sequence, classdict: Dict[str, Any], **kwargs):
        if not hasattr(sys.modules[__name__], 'Enum'):
            # Don't create metadata for Enum itself
            return super().__new__(cls, name, bases, dict(classdict), **kwargs)

        for base in (b for b in bases if issubclass(b, Serializer)):
            if base is not Enum:
                raise TypeError('enum classes can only inherit from Enum')
        args = {k: kwargs.pop(k) for k in cls._ENUM_ARGS if k in kwargs}
        return super().__new__(cls, name, bases, dict(classdict), metadata=EnumMetadata(
            members=types.MappingProxyType(classdict.members), **args), **kwargs)

    def __prepare__(name: str, bases: Sequence, **kwargs) -> MetaDict:
        def on_literal_add(classdict: MetaDict, key: str, value: Any):
            if not isinstance(value, (int, auto)):
                return value
            elif isinstance(value, auto):
                try:
                    value = last(classdict.members.values()) + 1
                except StopIteration:
                    value = 0
            # TODO: Create enum instances
            classdict.members[key] = value
            return MetaDict.ignore

        return MetaDict(name, on_literal_add)

    def __getattr__(cls, name: str) -> Any:
        try:
            return cls.__members__[name]
        except KeyError:
            return super().__getattr__(name)

    def __setattr__(cls, name: str, value: Any) -> None:
        if name in cls.__members__:
            raise AttributeError(f'{type_name(cls)}: cannot reassign Enum literal')
        return super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if name in cls.__members__:
            raise AttributeError(f'{type_name(cls)}: cannot delete Enum literal')
        return super().__delattr__(name)

    def __repr__(cls) -> str:
        return f'<enum {type_name(cls)}>'

    @strictproperty
    def __members__(cls) -> Mapping[str, 'Enum']:
        return cls.__metadata__.members


class Enum(Serializer, metaclass=EnumMeta):
    def __init__(self, value: 'Enum', *args, **kwargs):
        if isinstance(value, int):
            pass  # TODO: Find corresponding literal
        elif not isinstance(value, type(self)):
            raise TypeError(f'Expected {type_name(self)} literal or int, got {type_name(value)}')
        return super().__init__(value, *args, **kwargs)

    def _heracles_validate_(self, value: Optional[TypeUnion['Enum', int]] = None) -> int:
        value = self.__metadata__.serializer._heracles_validate_(value)
        # TODO: flags
        if value not in type(self).__members__.values():
            raise ValueError('value is not one of the enum members')
        return value

    def serialize_value(self, value: Optional[TypeUnion['Enum', int]], settings: Dict[str, Any] = None) -> bytes:
        return self.__metadata__.serializer.serialize_value(value, settings)

    # TODO: Return enum instance (also consider making literls Enum instances)
    def deserialize(self, raw_data: ByteString, settings: Dict[str, Any] = None) -> int:
        return self.__metadata__.serializer.deserialize(raw_data, settings)

    def get_literal_name(self, literal: int) -> str:
        # TODO: flags
        return first(k for k, v in type(self).__members__.items() if v == literal)

    def _heracles_render_(self, value: Optional[TypeUnion['Enum', int]] = None) -> str:
        value = self._get_serializer_value(value)
        self._heracles_validate_(value)
        return f'{type_name(self)}.{self.get_literal_name(value)} ({value})'

    def _heracles_compare_(self, other: TypeUnion['Enum', int], value: Optional[TypeUnion['Enum', int]] = None) -> bool:
        return self.__metadata__.serializer._heracles_compare_(other, value)

    def __int__(self) -> int:
        return self.value

    def __iter__(self) -> Iterator:
        return iter(type(self).__members__.values())
