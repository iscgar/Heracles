import sys
import types
import itertools
import collections
from typing import Any, ByteString, Dict, Iterator, Mapping, Optional, Sequence, Type, Union as TypeUnion

from .base import Serializer, SerializerMeta, SerializerMetadata, MetaDict, HiddenSentinal, byte_size, isvst, ishidden, iswrapper
from ._utils import last, type_name, is_type, as_type, get_as_value, copy_if_mutable, is_strict_subclass, is_classdef_in_classdict


__all__ = ['Struct', 'FieldVstError', 'UnknownFieldsError']


class FieldVstError(TypeError):
    def __init__(self, type_name: str, previous_vst: str, new_member: str):
        super().__init__(
            f'Field {type_name}.{previous_vst} is variable size and must be the'
            f' last member, but {type_name}.{new_member} was defined after it')


class UnknownFieldsError(ValueError):
    def __init__(self, typ: Type['Struct'], fields: Sequence[str]):
        typ_name = type_name(typ)
        field_names = ', '.join(f'`{f}`' for f in fields)
        if len(fields) > 1:
            message = f'The following fields are not memebrs of {typ_name}: {field_names}'
        else:
            message = f'The field {field_names} is not a member of {typ_name}'
        super().__init__(message)


class StructMetadata(SerializerMetadata):
    __slots__ = ('members',)

    def __init__(self, *, members: collections.OrderedDict):
        size = sum(map(byte_size, members.values()))
        super().__init__(size)
        self.members = members


class StructMeta(SerializerMeta):
    def __new__(cls, name: str, bases: Sequence, classdict: MetaDict) -> 'Struct':
        # Make sure that our only serializer bases are structs
        for base in (b for b in bases if is_strict_subclass(b, Serializer)):
            if base is not Struct:
                raise TypeError('structs can only inherit from Struct')
        classdict[SerializerMeta.METAATTR] = StructMetadata(
            members=types.MappingProxyType(classdict.members))

        new_type = super().__new__(cls, name, bases, dict(classdict))
        # Set the owner type for the new type's members
        for member in new_type.__members__.values():
            member.owner = new_type
        return new_type

    def __prepare__(name: str, bases: Sequence, **kwargs) -> MetaDict:
        def on_member_add(classdict: MetaDict, key: str, value: Any):
            if not issubclass(as_type(value), Serializer):
                return value
            elif is_classdef_in_classdict(classdict, key, value):
                return value

            members = classdict.members
            try:
                # Ensure that only the last member is VST
                last_name, last_value = last(members.items())
                if isvst(last_value):
                    raise FieldVstError(name, last_name, key)
            except StopIteration:
                pass

            if is_type(value):
                # Avoid creating unnecessary serializer instances where possible
                if value not in classdict.serializers_cache:
                    classdict.serializers_cache[value] = get_as_value(value)
                value = classdict.serializers_cache[value]

            if ishidden(value):
                key = HiddenSentinal()
            members[key] = StructMember(key, value)
            return MetaDict.ignore

        mapping = MetaDict(name, on_member_add)
        mapping.serializers_cache = {}
        return mapping

    @property
    def __isvst__(cls) -> bool:
        try:
            return isvst(last(cls.__members__.values()))
        except StopIteration:
            return False

    @property
    def __members__(cls):
        return cls.__metadata__.members

    def __getattr__(cls, name: str) -> Any:
        if name in cls:
            return cls.__members__[name]
        return super().__getattr__(name)

    def __setattr__(cls, name: str, value: Any) -> None:
        serializer = cls.__members__.get(name)
        if serializer is not None:
            serializer._heracles_validate_(value)
        super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if name in cls.__members__:
            raise AttributeError(f'{type_name(cls)}: cannot delete Struct member')
        super().__delattr__(name)

    def __contains__(cls, member) -> bool:
        return member in cls.__members__

    def __iter__(cls) -> Iterator:
        return (k for k in cls.__members__ if not isinstance(k, MetaDict.Hidden))

    def __repr__(cls) -> str:
        return f'<struct {type_name(cls)}>'


class StructMember(object):
    __slots__ = ('name', 'serializer', 'owner')

    def __init__(self, name: str, serializer: Serializer):
        self.name = name
        self.serializer = serializer

    @property
    def __isvst__(self) -> bool:
        return isvst(self.serializer)

    @property
    def __ishidden__(self) -> bool:
        return ishidden(self.serializer)

    @property
    def __iswrapper__(self) -> bool:
        return iswrapper(self.serializer)

    def __bytesize__(self, value: Optional[Any] = None) -> int:
        return byte_size(self.serializer, value)

    @property
    def offset(self) -> int:
        return sum(map(byte_size, itertools.takewhile(
            lambda m: m is not self, self.owner.__members__.values())))

    def __setattr__(self, name, value):
        if name not in self.__slots__ or hasattr(self, name):
            raise AttributeError(f'`{type_name(self)}` object does not support attribute setting')
        super().__setattr__(name, value)

    def __repr__(self) -> str:
        return f'<{type_name(self.owner)}.{self.name}: {self.serializer}>'


class Struct(Serializer, metaclass=StructMeta):
    def __init__(self, value: TypeUnion['Struct', Mapping[str, Serializer]] = {}, *args, **kwargs):
        # Support constructing from another Struct instance as well as from 
        # a dict supplying initial values for some or all of the members
        if not isinstance(value, dict) and type(value) != type(self):
            raise TypeError(f'Cannot construct {type_name(self)} from {type_name(value)}')

        for name, member in type(self).__members__.items():
            if ishidden(member):
                continue
            try:
                if isinstance(value, Struct):
                    member_value = getattr(value, name)
                else:
                    member_value = value.pop(name)
                setattr(self, name, member_value)
            except KeyError:
                setattr(self, name, member.serializer)

        if not isinstance(value, Struct) and value:
            raise UnknownFieldsError(self, value.keys())
        super().__init__(self, *args, *kwargs)

    def serialize_value(self, value: 'Struct', settings: Dict[str, Any] = None) -> bytes:
        if type(value) != type(self):
            raise TypeError(f'Cannot serialize value of {type_name(value)}')

        result = bytearray()
        for name, member in type(self).__members__.items():
            try:
                if ishidden(member):
                    data_piece = member.serializer.serialize(settings)
                else:
                    data_piece = member.serializer.serialize_value(
                        getattr(value, name), settings)
            except ValueError as e:
                raise ValueError(
                    f'Invalid data in field `{name}` of `{type_name(self)}`: {e.message}')
            result.extend(data_piece)
        return bytes(result)

    def deserialize(self, raw_data: ByteString, settings: Dict[str, Any] = None) -> 'Struct':
        if len(raw_data) < byte_size(type(self)):
            raise ValueError(f'Raw data size is too small for `{type_name(self)}`')

        members = {}
        for name, member in type(self).__members__.items():
            if isvst(member):
                data_piece = raw_data
            else:
                data_piece = raw_data[:byte_size(member)]
            value = member.serializer.deserialize(data_piece, settings)
            if not ishidden(member):
                members[name] = value
            raw_data = raw_data[len(data_piece):]
        return type(self)(members)

    def _heracles_validate_(self, value: Optional['Struct'] = None) -> 'Struct':
        value = self._get_serializer_value(value)
        if type(self) != type(value):
            raise ValueError(f'Cannot validate value of {type_name(value)}')

        for name, member in type(self).__members__.items():
            if ishidden(member):
                continue
            member.serializer._heracles_validate_(getattr(value, name))
        return value

    def _heracles_render_(self, value: Optional['Struct'] = None) -> str:
        def indent_text(text):
            return '\n'.join(f'  {line}' for line in text.split('\n'))

        value = self._get_serializer_value(value)
        if type(self) != type(value):
            raise ValueError(f'Cannot render value of {type_name(value)}')

        text = ',\n'.join(
                    indent_text(
                        f'{name}: {member.serializer._heracles_render_(getattr(value, name))}'
                        if not ishidden(member) else repr(member.serializer))
                    for name, member in type(self).__members__.items()
                )
        if text:
            text = f'\n{text}\n'
        return f'{type_name(self)} {{{text}}}'

    def _heracles_compare_(self, other: 'Struct', value: Optional['Struct'] = None) -> bool:
        value = self._get_serializer_value(value)
        if type(other) != type(self) != type(value):
            raise TypeError('Cannot compare values of other structs')
        return all(
            member.serializer._heracles_compare_(
                getattr(other, name), getattr(value, name))
            for name, member in type(self).__members__.items()
            if not ishidden(member))

    def __bytesize__(self, value: Optional['Struct'] = None) -> int:
        value = self._get_serializer_value(value)
        size = byte_size(type(self))

        if isvst(self):
            # Only the last member can be variable length
            name, member = last(type(self).__members__.items())
            diff = byte_size(member.serializer, getattr(value, name)) - byte_size(member)
            size += diff
        return size

    def __getattribute__(self, name: str) -> Any:
        value = super().__getattribute__(name)
        # Unwrap serializers that are wrappers around Python types on first access
        # in order to hide the somewhat inconvenient serializer interface from the user
        if isinstance(value, Serializer) and iswrapper(value) and name in self:
            value = copy_if_mutable(value.value)
            setattr(self, name, value)
        return value

    def __contains__(self, member: str) -> bool:
        return member in type(self)

    def __iter__(self) -> Iterator:
        return iter(type(self))
