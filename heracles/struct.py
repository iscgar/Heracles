import sys
import types
import itertools
import collections
from typing import Any, ByteString, Dict, Iterator, Mapping, Optional, Sequence, Type, Union as TypeUnion

from .base import Serializer, SerializerMeta, SerializerMetadata, MetaDict, HiddenSentinal
from ._utils import last, type_name, is_type, as_type, get_as_value, copy_if_mutable, is_strict_subclass, is_classdef_in_classdict


__all__ = ['Struct', 'BaseVstError', 'FieldVstError', 'UnknownFieldsError']


class BaseVstError(TypeError):
    def __init__(self, vst_base_name: str, vst_name: str):
        super().__init__(
            f'Base struct {vst_base_name} is variable size and must be the last'
            f' one with memebers in the inheritance chain, but {vst_name} was'
            ' found after it')


class FieldVstError(TypeError):
    def __init__(self, type_name: str, previous_vst: str, vst_name: str):
        super().__init__(
            f'Field {previous_vst} of type {type_name} is variable size and'
            f' must be the last member, but {vst_name} was defined after it')


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
        size = sum(m.byte_size for m in members.values())
        super().__init__(size)
        self.members = members


class StructMeta(SerializerMeta):
    def __new__(cls, name: str, bases: Sequence, classdict: MetaDict) -> 'Struct':
        last_base = None
        metamembers = MetaDict(name)  # Use a MetaDict to ensure

        # Make sure that our only serializer bases are structs
        for base in (b for b in bases if is_strict_subclass(b, Serializer)):
            if not issubclass(base, Struct):
                raise TypeError('Struct can only inherit from other structs')
            # Fail if we encountered a VST base in the previous iteration
            elif last_base:
                raise BaseVstError(type_name(last_base), type_name(base))
            elif base.is_vst:
                last_base = base
            metamembers.update(base._members_)

        # Fail if we have a VST base
        if last_base:
            last_value = last(classdict.members.values())
            if last_value.is_vst:
                raise BaseVstError(type_name(last_base), name)
        metamembers.update(classdict.members)

        classdict.update({
            SerializerMeta.METAATTR: StructMetadata(
                members=types.MappingProxyType(metamembers)),
        })

        new_type = super().__new__(cls, name, bases, dict(classdict))
        # Set the owner type for the new type's members
        for member in classdict.members.values():
            member.owner = new_type
        return new_type

    def __prepare__(name: str, bases: Sequence, **kwargs) -> MetaDict:
        def on_member_add(classdict: MetaDict, key: str, value: Any):
            if not issubclass(as_type(value), Serializer):
                return value
            elif is_classdef_in_classdict(classdict, key, value):
                return value
            members = classdict.members
            if members:
                last_name, last_value = last(members.items())
                if last_value.is_vst:
                    raise FieldVstError(name, key, last_name)
            if is_type(value):
                # Avoid creating unnecessary serializer instances where possible
                if value not in classdict.serializers_cache:
                    classdict.serializers_cache[value] = get_as_value(value)
                value = classdict.serializers_cache[value]
            if type(value).is_hidden:
                key = HiddenSentinal()
            members[key] = StructMember(key, value)
            return MetaDict.ignore
        mapping = MetaDict(name, on_member_add)
        mapping.serializers_cache = {}
        return mapping

    @property
    def _members_(cls):
        return cls._metadata_.members

    def __getattr__(cls, name: str) -> Any:
        if name in cls:
            return cls._members_[name]
        return super().__getattr__(name)

    def __setattr__(cls, name: str, value: Any) -> None:
        serializer = cls._members_.get(name)
        if serializer is not None:
            serializer._heracles_validate_(value)
        super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if name in cls._members_:
            raise AttributeError(f'{type_name(cls)}: cannot delete Struct member')
        super().__delattr__(name)

    def __contains__(cls, member) -> bool:
        return member in cls._members_

    def __iter__(cls) -> Iterator:
        return (k for k in cls._members_ if not isinstance(k, MetaDict.Hidden))

    def __repr__(cls) -> str:
        return f'<struct {type_name(cls)}>'


class StructMember(object):
    __slots__ = ('name', 'serializer', 'owner')

    def __init__(self, name: str, serializer: Serializer):
        self.name = name
        self.serializer = serializer

    @property
    def is_vst(self) -> bool:
        return self.serializer._heracles_vst_()

    @property
    def is_hidden(self) -> bool:
        return self.serializer._heracles_hidden_()

    @property
    def byte_size(self) -> int:
        return self.serializer._heracles_bytesize_()

    @property
    def offset(self) -> int:
        return sum(
            member.byte_size for member in itertools.takewhile(
                lambda m: m is not self, self.owner._members_.values()))

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

        for name, member in type(self)._members_.items():
            if member.is_hidden:
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

    @classmethod
    def _heracles_vst_(cls) -> bool:
        try:
            return last(cls._members_.values()).is_vst
        except StopIteration:
            return False

    def serialize_value(self, value: 'Struct', settings: Dict[str, Any] = None) -> bytes:
        if type(value) != type(self):
            raise TypeError(f'Cannot serialize value of {type_name(value)}')

        result = bytearray()
        for name, member in type(self)._members_.items():
            try:
                if member.is_hidden:
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
        if len(raw_data) < type(self).byte_size:
            raise ValueError(f'Raw data size is too small for `{type_name(self)}`')

        members = {}
        for name, member in type(self)._members_.items():
            if member.is_vst:
                data_piece = raw_data
            else:
                data_piece = raw_data[:member.byte_size]
            value = member.serializer.deserialize(data_piece, settings)
            if not member.is_hidden:
                members[name] = value
            raw_data = raw_data[len(data_piece):]
        return type(self)(members)

    def _heracles_validate_(self, value: Optional['Struct'] = None) -> 'Struct':
        value = self._get_serializer_value(value)
        if type(self) != type(value):
            raise ValueError(f'Cannot validate value of {type_name(value)}')

        for name, member in type(self)._members_.items():
            if member.is_hidden:
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
                        if not member.is_hidden else repr(member.serializer))
                    for name, member in type(self)._members_.items()
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
            for name, member in type(self)._members_.items()
            if not member.is_hidden)

    def _heracles_bytesize_(self, value: Optional['Struct'] = None) -> int:
        value = self._get_serializer_value(value)
        size = super()._heracles_bytesize_(value)

        if self._heracles_vst_():
            # Only the last member can be variable length
            name, member = last(type(self)._members_.items())
            diff = member.serializer._heracles_bytesize_(getattr(value, name)) - member.byte_size
            size += diff
        return size

    def __getattribute__(self, name: str) -> Any:
        value = super().__getattribute__(name)
        # Unwrap serializers that are wrappers around Python types on first access
        # in order to hide the somewhat inconvenient serializer interface from the user
        if issubclass(as_type(value), Serializer) and value._heracles_wrapper_() and name in self:
            value = copy_if_mutable(value.value)
            setattr(self, name, value)
        return value

    def __contains__(self, member: str) -> bool:
        return member in type(self)

    def __iter__(self) -> Iterator:
        return iter(type(self))
