import inspect
import itertools
import collections
from typing import Any, ByteString, Dict, Iterator, Mapping, Optional, Sequence, Type

from .base import Serializer, SerializerMeta, SerializerMetadata, MetaDict
from ._utils import last, get_type_name, get_as_type, get_as_value, is_strict_subclass, is_class_in_class_body, instanceoverride


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
        type_name = get_type_name(typ)
        field_names = ', '.join(f'`{f}`' for f in fields)
        if len(fields) > 1:
            message = f'The fields {field_names} are not memebrs of {type_name}'
        else:
            message = f'The field {field_names} is not a member of {type_name}'
        super().__init__(message)


class StructMeta(SerializerMeta):
    def __new__(cls, name: str, bases: Sequence, classdict: MetaDict) -> 'Struct':
        if not classdict.get(SerializerMeta.METAATTR):
            size = 0
            last_serializer = None
            metamembers = MetaDict(name)

            for base in (b for b in bases if is_strict_subclass(b, Serializer)):
                if not issubclass(base, Struct):
                    raise TypeError('Struct can only inherit from other structs')
                elif last_serializer and base._heracles_members_():
                    raise BaseVstError(get_type_name(last_serializer), get_type_name(base))
                elif base._heracles_vst_():
                    last_serializer = base

                metamembers.update(base._heracles_members_())
            
            if last_serializer and classdict.members:
                last_name, last_value = last(classdict.members.items())
                if last_value._heracles_vst_():
                    raise BaseVstError(get_type_name(last_serializer), name)
            metamembers.update(classdict.members)
            metamembers = metamembers.members

            classdict.update({
                SerializerMeta.METAATTR: SerializerMetadata(
                    sum(m._heracles_bytesize_() for m in metamembers.values()),
                    members=metamembers),
            })

        return super().__new__(
            cls, name, bases, collections.OrderedDict(classdict))

    def __prepare__(name: str, bases: Sequence, **kwargs) -> MetaDict:
        def on_member_add(classdict: MetaDict, key: str, value: Any):
            if not issubclass(get_as_type(value), Serializer):
                return None
            elif is_class_in_class_body(classdict, key, value):
                return None

            members = classdict.members
            if members:
                last_name, last_value = last(members.items())
                if last_value._heracles_vst_():
                    raise FieldVstError(name, key, last_name)
            return get_as_value(value)

        return MetaDict(name, on_member_add)

    def __setattr__(cls, name: str, value: Any) -> None:
        serializer = cls._heracles_members_().get(name)
        if serializer is not None:
            serializer._heracles_validate_(value)
        super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if name in cls._heracles_members_():
            raise AttributeError(f'{get_type_name(cls)}: cannot delete Struct member')
        super().__delattr__(name)

    def __contains__(cls, member) -> bool:
        return member in cls._heracles_members_()

    def __iter__(cls) -> Iterator:
        return iter(cls._heracles_members_().keys())

    def __repr__(cls) -> str:
        return f'<struct {get_type_name(cls)}>'


class Struct(Serializer, metaclass=StructMeta):
    def __init__(self, value: Mapping[str, Serializer] = {}, *args, **kwargs):
        if not isinstance(value, dict) and type(value) != type(self):
            raise TypeError(f'Cannot construct {get_type_name(self)} from {get_type_name(value)}')

        for name, serializer in self._heracles_members_().items():
            try:
                setattr(self, name, value[name])
                if not isinstance(value, Struct):
                    del value[name]
            except KeyError:
                # XXX: deepcopy the serializer value instead?
                setattr(self, name, serializer)

        if not isinstance(value, Struct) and value:
            raise UnknownFieldsError(self, value.keys())
        super().__init__(self, *args, *kwargs)

    @classmethod
    def _heracles_members_(cls) -> collections.OrderedDict:
        return cls._heracles_metadata_().members

    @classmethod
    def _heracles_vst_(cls) -> bool:
        members = cls._heracles_members_()
        return members and last(members.values())._heracles_vst_()

    @classmethod
    def offsetof(cls, member: str) -> int:
        members = cls._heracles_members_()
        if member not in members:
            raise UnknownFieldsError(cls, (member,))
        return sum(members[k]._heracles_bytesize_() 
            for k in itertools.takewhile(lambda k: k != member, members))

    def serialize_value(self, value: 'Struct', settings: Dict[str, Any] = None) -> bytes:
        if type(value) != type(self):
            raise TypeError('Cannot serialize values of other types')

        result = bytearray()
        for name, serializer in self._heracles_members_().items():
            try:
                result.extend(serializer.serialize_value(getattr(value, name), settings))
            except ValueError as e:
                raise ValueError(
                    f'Invalid data in field `{name}` of `{get_type_name(self)}`: {e.message}')
        return bytes(result)

    def deserialize(self, raw_data: ByteString, settings: Dict[str, Any] = None) -> 'Struct':
        if len(raw_data) < self._heracles_bytesize_():
            raise ValueError(
                f'Raw data size is too small for the struct `{get_type_name(self)}`')

        members = {}
        for name, serializer in self._heracles_members_().items():
            if serializer._heracles_vst_():
                data_piece = raw_data
            else:
                data_piece = raw_data[:serializer._heracles_bytesize_()]
            value = serializer.deserialize(data_piece, settings)

            if not serializer._heracles_hidden_():
                members[name] = value
            
            raw_data = raw_data[len(data_piece):]
        return type(self)(members)

    def _heracles_validate_(self, value: Optional['Struct'] = None) -> 'Struct':
        value = self._get_serializer_value(value)
        if type(self) != type(value):
            raise ValueError('Cannot validate values of other types')

        for name, serializer in self._heracles_members_().items():
            serializer._heracles_validate_(getattr(value, name))
        return value

    def _heracles_render_(self, value: Optional['Struct'] = None) -> str:
        def indent_text(text):
            return '\n'.join(f'  {line}' for line in text.split('\n'))

        value = self._get_serializer_value(value)
        if type(self) != type(value):
            raise ValueError('Cannot render values of other types')

        text = ',\n'.join(
                    indent_text(
                        f'{name}: {serializer._heracles_render_(getattr(value, name))}'
                        if not serializer._heracles_hidden_() else repr(serializer))
                    for name, serializer in self._heracles_members_().items()
                )
        if text:
            text = f'\n{text}\n'
        return f'{get_type_name(self)} {{{text}}}'

    def _heracles_compare_(self, other: 'Struct', value: Optional['Struct'] = None) -> bool:
        value = self._get_serializer_value(value)
        if type(other) != type(self) != type(value):
            raise TypeError('Cannot compare values of other types')
        return all(
            serializer._heracles_compare_(getattr(other, name), getattr(value, name))
            for name, serializer in self._heracles_members_().items()
            if not serializer._heracles_hidden_())

    @instanceoverride
    def _heracles_bytesize_(self, value: Optional['Struct'] = None) -> int:
        value = self._get_serializer_value(value)
        size = super()._heracles_bytesize_(value)

        if self._heracles_vst_():
            # Only the last member can be variable length
            name, serializer = last(self._heracles_members_().items())
            size += serializer._heracles_bytesize_(getattr(value, name)) - serializer._heracles_bytesize_()
        return size

    def __getitem__(self, member) -> Any:
        # XXX: override __getattribute__ and return values instead of serializers?
        if member not in self:
            raise KeyError(f'{member} is not a member of {get_type_name(self)}')
        return getattr(self, member)

    def __contains__(self, member) -> bool:
        return member in type(self)

    def __iter__(self) -> Iterator:
        return iter(type(self))
