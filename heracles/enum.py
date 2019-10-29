import sys
import collections
from typing import Any, ByteString, Dict, Iterator, Mapping, Optional, Sequence, Type, Union as TypeUnion

from .base import Serializer, SerializerMeta, SerializerMetadata, MetaDict, byte_size
from .scalars import *
from ._utils import first, last, type_name, as_type, get_as_value, func_params, ParameterKind

__all__ = ['Enum', 'auto']


class auto(object):
    pass


class EnumMetadata(SerializerMetadata):
    __slots__ = ('serializer', 'flags', 'literals')
    _VALID_UNDERLYING_TYPES = (
        u8, u16, u32, u64, i8, i16, i32, i64,
        u8_le, u16_le, u32_le, u64_le, i8_le, i16_le, i32_le, i64_le,
        u8_be, u16_be, u32_be, u64_be, i8_be, i16_be, i32_be, i64_be)

    def __init__(self, *, literals: collections.OrderedDict, underlying: Type[Scalar] = i32, flags: bool = False):
        if underlying not in self._VALID_UNDERLYING_TYPES:
            raise TypeError(f'Invalid underlying type for Enum: {type_name(underlying)}')
        serializer = get_as_value(underlying)
        try:
            for k, v in literals.items():
                serializer._heracles_validate_(v)
        except ValueError as e:
            raise ValueError(f'Invalid value for literal {v}: {e.message}')
        super().__init__(byte_size(serializer))
        self.flags = flags
        self.serializer = serializer
        self.literals = literals


class EnumMeta(SerializerMeta):
    _ENUM_ARGS = tuple(
        p.name for p in func_params(EnumMetadata.__init__, ParameterKind.KEYWORD_ONLY))

    def __new__(cls, name: str, bases: Sequence, classdict: Dict[str, Any], **kwargs):
        if hasattr(sys.modules[__name__], 'Enum'):
            for base in (b for b in bases if issubclass(b, Serializer)):
                if base is not Enum:
                    raise TypeError('enum classes can only inherit from Enum')

            args = {k: kwargs.pop(k) for k in cls._ENUM_ARGS if k in kwargs}
            classdict.update({
                SerializerMeta.METAATTR:
                    EnumMetadata(literals=classdict.members, **args),
            })

        return super().__new__(cls, name, bases, dict(classdict), **kwargs)

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
            return cls.literals()[name]
        except KeyError:
            return super().__getattr__(name)

    def __setattr__(cls, name: str, value: Any) -> None:
        if name in cls.literals():
            raise AttributeError(f'{type_name(cls)}: cannot reassign Enum literal')
        super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if name in cls.literals():
            raise AttributeError(f'{type_name(cls)}: cannot delete Enum literal')
        super().__delattr__(name)

    def __repr__(cls) -> str:
        return f'<enum {type_name(cls)}>'


class Enum(Serializer, metaclass=EnumMeta):
    def __init__(self, value=None, *args, **kwargs):
        # TODO: Forbid constructing Enum without a value
        if value is None:
            if self.literals():
                value = first(self.literals().values())
            else:
                value = 0
        super().__init__(value, *args, **kwargs)

    @classmethod
    def literals(cls) -> Mapping[str, int]:
        return cls.__metadata__.literals

    def _heracles_validate_(self, value: Optional[TypeUnion['Enum', int]] = None) -> int:
        value = self.__metadata__.serializer._heracles_validate_(value)
        # TODO: flags
        if value not in self.literals().values():
            raise ValueError('value is not one of the enum literals')
        return value

    def serialize_value(self, value: Optional[TypeUnion['Enum', int]], settings: Dict[str, Any] = None) -> bytes:
        return self.__metadata__.serializer.serialize_value(value, settings)

    # TODO: Return enum instance (also consider making literls Enum instances)
    def deserialize(self, raw_data: ByteString, settings: Dict[str, Any] = None) -> int:
        return self.__metadata__.serializer.deserialize(raw_data, settings)

    def get_literal_name(self, literal: int) -> str:
        # TODO: flags
        return first(k for k, v in self.literals().items() if v == literal)

    def _heracles_render_(self, value: Optional[TypeUnion['Enum', int]] = None) -> str:
        value = self._get_serializer_value(value)
        self._heracles_validate_(value)
        return f'{type_name(self)}.{self.get_literal_name(value)} ({value})'

    def _heracles_compare_(self, other: TypeUnion['Enum', int], value: Optional[TypeUnion['Enum', int]] = None) -> bool:
        return self.__metadata__.serializer._heracles_compare_(other, value)

    def __int__(self) -> int:
        return self.value

    def __iter__(self) -> Iterator:
        return iter(self.literals().values())
