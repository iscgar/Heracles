import collections
import itertools
import typing

from .base import Serializer, SerializerMeta, SerializerMetadata, MetaDict
from .utils import last, is_strict_subclass, get_type_name, get_as_type, get_as_value


__all__ = ['Struct']


class StructMeta(SerializerMeta):
    def __new__(cls, name: str, bases: typing.Sequence, classdict: typing.Dict[str, typing.Any]):
        if not classdict.get(SerializerMeta.METAATTR):
            size = 0
            last_serializer = None
            members = collections.OrderedDict()

            for base in bases:
                if not is_strict_subclass(base, Serializer):
                    continue
                
                if not issubclass(base, Struct):
                    raise TypeError('Struct can only derive other structs')

                size += cls._update_members(
                    name, members, base, base.members(), classdict, last_serializer)
                
                if not base.constant_size():
                    last_serializer = base

            size += cls._update_members(
                name, members, cls, classdict.members, classdict, last_serializer)

            classdict.update({
                SerializerMeta.METAATTR: SerializerMetadata(
                    size, members=members),
            })

        return super().__new__(
            cls, name, bases, collections.OrderedDict(classdict))
    
    @staticmethod
    def _update_members(tname: str, members, base, type_members, classdict, last_serializer) -> int:
        if last_serializer and type_members:
            raise TypeError(f"Base struct `{get_type_name(last_serializer)}` \
is variable length, but it's not the last one to have members")
        elif issubclass(base, Serializer) and not base.constant_size():
            last_serializer = base

        size = 0
        for name, value in type_members.items():
            if name in members:
                if not value.hidden():
                    raise TypeError(f'field `{name}` of type `{get_type_name(base)}` \
overrides an existing member in the bases of `{tname}`')
                    
                name = classdict.gen_hidden_name(name, len(members))

            members[name] = value
            size += len(value)
        
        return size

    def __prepare__(name: str, bases: typing.Sequence, **kwargs) -> MetaDict:
        def on_member_add(members: typing.Dict[str, Serializer], name: str, value: typing.Any):
            if not issubclass(get_as_type(value), Serializer):
                return None
            
            if members:
                last_name, last_value = last(members.items())
                if not last_value.constant_size():
                    raise TypeError(f'Field `{last_name}` is variable length \
but the field `{name}` was defined right after it')

            return get_as_value(value)

        return MetaDict(name, on_member_add)

    def __setattr__(cls, name: str, value: typing.Any) -> None:
        serializer = cls.members().get(name)
        if serializer is not None:
            serializer.validate(value)
        super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if name in cls.members():
            raise AttributeError(f'{get_type_name(cls)}: cannot delete Struct member')
        super().__delattr__(name)

    def __repr__(cls) -> str:
        return f'<struct {get_type_name(cls)}>'


class Struct(Serializer, metaclass=StructMeta):
    def __init__(self, *args, **kwargs):
        for name, serializer in self.members().items():
            # Accept non-default values through the keyword arguments.
            if name in kwargs:
                setattr(self, name, kwargs[name])
                del kwargs[name]
            else:
                setattr(self, name, serializer)

        super().__init__(self, *args, *kwargs)

    @classmethod
    def members(cls) -> collections.OrderedDict:
        return cls.metadata().members

    @classmethod
    def constant_size(cls) -> bool:
        members = cls.members()
        return not members or last(members.values()).constant_size()

    @classmethod
    def offsetof(cls, member: str) -> int:
        members = cls.members()
        if member not in members:
            raise ValueError(f'Field `{member} is not part of `{get_type_name(cls)}')

        return sum(len(members[k]) for k in itertools.takewhile(lambda k: k != member, members))

    def serialize_value(self, value: 'Struct', settings: typing.Dict[str, typing.Any]=None) -> bytes:
        assert issubclass(type(value), Struct)

        serialized_fields = []
        for name, serializer in self.members().items():
            try:
                serialized_fields.append(
                    serializer.serialize_value(getattr(value, name), settings))
            except ValueError as e:
                raise ValueError(
                    f'Invalid data in field `{name}` of `{get_type_name(self)}`: {e.message}')

        return b''.join(serialized_fields)

    def deserialize(self, raw_data: typing.ByteString, settings: typing.Dict[str, typing.Any]=None):
        if len(raw_data) < len(self):
            raise ValueError(
                f'Raw data size is too small for the struct `{get_type_name(self)}`')

        members = {}
        for name, serializer in self.members().items():
            data_piece = raw_data[:len(serializer) if serializer.constant_size() else None]
            value = serializer.deserialize(data_piece, settings)

            if not serializer.hidden():
                members[name] = value
            
            raw_data = raw_data[len(data_piece):]

        return type(self)(**members)

    def validate(self, value: typing.Optional['Struct']=None) -> 'Struct':
        value = self.get_serializer_value(value)
        if type(self) != type(value):
            raise ValueError('Cannot validate non-Struct types')

        for name, serializer in self.members().items():
            serializer.validate(getattr(value, name))

        return value

    def render(self, value: typing.Optional['Struct']=None) -> str:
        def indent_text(text):
            return '\n'.join(f'    {line}' for line in text.split('\n'))

        value = self.get_serializer_value(value)
        if type(self) != type(value):
            raise ValueError('Cannot render value of different type')

        text = '\n'.join(
                    indent_text(
                        f'{name}: {serializer.render(getattr(value, name))}'
                        if not serializer.hidden() else repr(serializer))
                    for name, serializer in self.members().items()
                )
        return f'{get_type_name(self)} {{\n{text}\n}}'

    def compare(self, other: 'Struct', value: typing.Optional['Struct']=None) -> bool:
        value == self.get_serializer_value(value)
        if type(other) != type(self) != type(value):
            raise ValueError('Cannot compare structs of differing types')

        return all(
            serializer.compare(getattr(other, name), getattr(value, name))
            for name, serializer in self.members().items()
            if not serializer.hidden())

    def __len__(self) -> int:
        size = super().__len__()

        if not self.constant_size():
            # Only the last member can be variable length
            name, serializer = last(self.members().items())
            size -= len(get_as_type(serializer))
            size += len(serializer.get_serializer_value(getattr(self, name)))

        return size

    def __iter__(self):
        for key in self.members():
            value = getattr(self, key)
            if issubclass(type(value), Struct):
                yield key, dict(value)
            elif type(value) in (list, tuple):
                if value and issubclass(type(value[0]), Struct):
                    yield key, [dict(d) for d in value]
                else:
                    yield key, list(value)
            else:
                yield key, value

