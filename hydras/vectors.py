import itertools

from .base import Serializer, SerializerMeta, SerializerMetadata
from .scalars import u8
from .utils import get_type_name, get_as_type, get_as_value, value_or_default, padto
from .validators import ExactValueValidator


class _Array(Serializer):
    def __init__(self, value=(), *args, **kwargs):
        return super(_Array, self).__init__(value, *args, **kwargs)

    def __len__(self) -> int:
        size = len(type(self))

        if not self.constant_size():
            size = max(self._get_value_size(), size)

        return size

    def _get_value_size(self, value=None) -> int:
        value = self.get_serializer_value(value)
        return len(value) * len(self.serializer)

    def _get_elements_count(self):
        return len(self) // len(self.serializer)

    def validate(self, value=None):
        value = self.get_serializer_value(value)
        if self._get_value_size(value) > len(self):
            raise ValueError('Assigned value size exceeds array size')

        for i in value:
            self.serializer.validate(i)

    def serialize_value(self, value, settings=None) -> bytes:
        if value_or_default(settings, {}).get('validate_on_serialize'):
            self.validate()

        serialized = b''.join(self.serializer.serialize_value(v, settings) for v in value)
        remaining_elements_count = (len(self) - len(serialized)) // len(self.serializer)
        padding = b''.join(self.serializer.serialize() for _ in range(remaining_elements_count))

        return serialized + padding

    def deserialize(self, raw_data, settings=None):
        if len(raw_data) != len(self):
            raise ValueError('Raw data is not in the correct length')

        return self._deserialize(raw_data, settings)

    def _deserialize(self, raw_data, settings=None):
        if len(raw_data) % len(self.serializer) != 0:
            raise ValueError('Raw data size isn\'t divisible by array element size')

        values_iterator = (
            self.serializer.deserialize(chunk, settings)
            for chunk in iter_chunks(raw_data, len(self.serializer)))

        if isinstance(self.value, bytes):
            value = b''.join(values_iterator)
        elif isinstance(self.value, str):
            value = ''.join(values_iterator)
        else:
            value = type(self.value)(values_iterator)

        return value

    def __eq__(self, other) -> bool:
        if len(other) > len(self):
            return False

        return all(a == b for a, b in itertools.zip_longest(
            self, other, fillvalue=self.serializer))

    def _repr_array_value(self) -> str:
        def as_int(v) -> int:
            return ord(v) if isinstance(v, (bytes, str)) else int(v)

        if isinstance(self.value, bytes):
            return repr(b''.join(chr(as_int(v)).encode('ascii') for v in self.value))
        elif isinstance(self.value, str):
            return repr(''.join(chr(as_int(v)) for v in self.value))
        else:
            return '{{{}}}'.format(', '.join(repr(v) for v in self.value))

    def __repr__(self) -> str:
        return f'{get_type_name(self)}({self._get_elements_count()}, {self._repr_array_value()})'

    def __iter__(self):
        for v in self.value:
            yield self.serializer.get_serializer_value(v)

        for _ in range(len(self.value), self._get_elements_count()):
            yield self.serializer.value


class _Padding(_Array):
    def __init__(self, *args, **kwargs):
        return super(_Padding, self).__init__(b'', *args, **kwargs)

    @classmethod
    def hidden(cls):
        return True

    def deserialize(self, raw_data, settings=None):
        super(_Padding, self).deserialize(raw_data, settings)
        return b''

    def __repr__(self):
        return f'{get_type_name(self)}({self.serializer.serialize()}, {len(self)})'


class _VariableArray(_Array):
    def deserialize(self, raw_data, settings=None):
        if len(raw_data) > self.max_length * len(self.serializer):
            raise ValueError('Raw data is too long for variable length array')
        elif len(raw_data) < self.min_length * len(self.serializer):
            raise ValueError('Raw data is too short for variable length array')

        return self._deserialize(raw_data, settings)

    def __eq__(self, other) -> bool:
        if other is None or self.get_serializer_value(other) != len(self):
            return False

        return all(a == b for a, b in itertools.izip_longest(
            self, other, fillvalue=self.serializer))

    @classmethod
    def constant_size(cls) -> bool:
        return False

    def validate(self, value=None):
        value = self.get_serializer_value(value)
        if not self.max_length >= len(value) >= self.min_length:
            raise ValueError(
                f'Data size ({len(value)}) is out of bounds for VLA [{self.min_length}, {self.max_length}]')

        for i in value:
            self.serializer.validate(i)

    def __repr__(self) -> str:
        return f'{get_type_name(self)}([{self.min_length}:{self.max_length}], {self._repr_array_value()} ({len(self.value)}))'


def _array(cls, name, size, items_type):
    if not issubclass(get_as_type(items_type), Serializer):
        raise TypeError('Array item type should be a Serializer')

    serializer = get_as_value(items_type)

    if not serializer.constant_size():
        raise TypeError('Array item type must not be variable length')

    return type(name, (cls,), {
            SerializerMeta.METAATTR: SerializerMetadata(
                name, size * len(serializer)),
            'serializer': serializer,
            })


def Array(size, items_type=u8):
    return _array(_Array, 'Array', size, items_type)


def VariableArray(min_length, max_length, items_type=u8):
    if not isinstance(min_length, int) or not isinstance(max_length, int):
        raise ValueError('VariableArray min and max length must be integers')

    if not 0 <= min_length < max_length:
        raise ValueError('VariableArray min length must be smaller than max length')

    result = _array(_VariableArray, 'VariableArray', min_length, items_type)
    result.min_length = min_length
    result.max_length = max_length
    return result


def Padding(size, pad_value=0):
    return _array(_Padding, 'Padding', size, u8(
        pad_value, validator=ExactValueValidator(pad_value)))
