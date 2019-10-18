import collections
import itertools
from typing import Dict, Any
from .base import Serializer, SerializerMeta, SerializerMetadata
from .utils import last, get_type_name, get_as_type, get_as_value, MetaDict

class StructMeta(SerializerMeta):
    def __new__(cls, name, bases, classdict):
        if not hasattr(cls, SerializerMeta.METAATTR) or cls.metadata().name != name:
            size = 0
            vl_fmt = False
            members_set = set()
            members = []

            for b in (b for b in bases if hasattr(b, 'members')):
                for k, v in b.members():
                    if vl_fmt:
                        raise TypeError(
                            f'field `{vl_fmt}` of type `{get_type_name(b)}` \
in the bases of `{get_type_name(cls)}` is variable length, but only the last \
field is allowed to be variable length')

                    if not v.hidden() and k in members_set:
                        raise TypeError(
                            f'field `{k}` of type `{get_type_name(b)}` \
overrides an existing member in the bases of `{get_type_name(cls)}`')

                    members_set.add(k)
                    members.append((k, v))
                    if not v.constant_size():
                        vl_fmt = k
                    size += len(v)

        
            for k, v in classdict.members:
                if vl_fmt:
                    raise TypeError(f'field `{vl_fmt}` of type \
`{get_type_name(cls)}` is variable length, but only the last \
field is allowed to be variable length')

                if k and k in members_set:
                    raise TypeError(
                        f'field `{k}` overrides an existing \
member of `{get_type_name(cls)}`')

                members_set.add(k)
                members.append((k, v))
                if not v.constant_size():
                    vl_fmt = k
                size += len(v)

            classdict.update({
                SerializerMeta.METAATTR: SerializerMetadata(
                    name, size, members=collections.OrderedDict(members)),
            })

        classdict = collections.OrderedDict(classdict)
        return SerializerMeta.__new__(cls, name, bases, classdict)

    def __prepare__(cls, bases, **kwargs) -> MetaDict:
        return MetaDict(
            lambda meta, name, value: get_as_value(value)
                if issubclass(get_as_type(value), Serializer) else None)


class Struct(Serializer, metaclass=StructMeta):
    def __init__(self, **kwargs):
        # Initialize a copy of the data properties.
        for name, serializer in self.members().items():
            # Accept a non-default value through the keyword arguments.
            if name in kwargs:
                setattr(self, name, kwargs[name])
            else:
                setattr(self, name, serializer)

        super(Struct, self).__init__(value=self)

    @classmethod
    def members(cls) -> collections.OrderedDict:
        return cls.metadata().members

    @classmethod
    def constant_size(cls) -> bool:
        members = cls.members()
        return not members or last(members.values()).constant_size()

    @classmethod
    def offsetof(cls, member: str) -> int:
        members = self.members()
        if member not in members:
            raise ValueError(f'Field `{member} is not part of type `{get_type_name(self)}')

        return sum(len(members[k]) for k in itertools.takewhile(lambda k: k != member, members))

    def serialize_value(self, value, settings: Dict[str, Any]=None) -> bytes:
        assert issubclass(type(value), Struct)

        serialized_fields = []
        for name, serializer in self.members().items():
            try:
                serialized_fields.append(
                    serializer.serialize_value(getattr(value, name), settings))
            except ValueError as e:
                raise ValueError(
                    f'Invalid data in field `{name}` of type `{get_type_name(self)}`: {e.message}')

        return b''.join(serialized_fields)

    def deserialize(self, raw_data, settings=None):
        if not isinstance(raw_data, bytes):
            raise ValueError(f'Expected a byte string of raw data, got `{get_type_name(raw_data)}`')

        if len(raw_data) < len(self):
            raise ValueError(
                f'Raw data size is too small for a struct of type `{get_type_name(self)}`')

        members = {}
        for name, serializer in self.members().items():
            data_piece = raw_data[:len(serializer) if serializer.constant_size() else None]
            value = serializer.deserialize(data_piece, settings)

            if not serializer.hidden():
                members[name] = value
            
            raw_data = raw_data[len(data_piece):]

        return type(self)(**members)

    def validate(self, value=None):
        value = self.get_serializer_value(value)
        for name, serializer in self.members().items():
            serializer.validate(getattr(value, name))

    def _get_field_serializer(self, field, serializer):
        value = getattr(self, field)
        if value is None:
            return get_as_value(serializer)
        ser_typ = get_as_type(serializer)
        if get_as_type(value) != ser_typ:
            value = ser_typ(value)
        return value

    def __len__(self) -> int:
        size = len(super(Struct, self))

        if not self.constant_size():
            # Only the last member can be variable length
            name, serializer = last(self.members().items())
            size += len(serializer)

        return size

    def __eq__(self, other) -> bool:
        if type(other) != type(self):
            raise TypeError('Cannot compare structs of differing types')

        return all(
            self._get_field_serializer(serializer) == getattr(other, name)
            for name, serializer in cls.members().items()
            if not serializer.hidden())

    def __setattr__(self, name, value):
        serializer = self.members().get(name)
        if serializer is not None:
            serializer.validate(value)

        return super(Struct, self).__setattr__(name, value)

    def __delattr__(self, name):
        if name in self.members():
            raise RuntimeError(f'Cannot delete struct member `{name}`')
        return super(Struct, self).__delattr__(name)

    def __repr__(self) -> str:
        """ Create a string representation of the struct's data. """
        def indent_text(text):
            return '\n'.join(f'    {line}' for line in text.split('\n'))

        text = '\n'.join(
                    indent_text(
                        f'{name}: {self._get_field_serializer(name, serializer)}'
                        if not serializer.hidden() else repr(serializer))
                    for name, serializer in self.members().items()
                )
        return f'{get_type_name(self)} {{\n{text}\n}}'

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

