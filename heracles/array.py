import sys
import copy
import itertools
from typing import Any, Dict, ByteString, Iterator, Optional, Sequence, Type, Union as TypeUnion

from .base import Serializer, SerializerMeta, SerializerMetadata
from ._utils import get_type_name, get_as_type, get_as_value, value_or_default, iter_chunks, instanceoverride

__all__ = ['Array']


class ArrayMeta(SerializerMeta):
    def __getitem__(cls, args):
        is_array_type = (
            issubclass(cls, Array) and 
            getattr(cls, '__module__', None) == __name__ and
            getattr(sys.modules[__name__], get_type_name(cls), None) == cls)

        if not is_array_type or not isinstance(args, tuple) or len(args) != 2:
            return super().__getitem__(args)
        
        size, serializer = args
        if isinstance(size, int):
            if size < 0:
                raise ValueError(f'Array size must not be negative, got {size}')
            size_min = size_max = size
        elif isinstance(size, slice):
            if size.step is not None:
                raise ValueError('Cannot supply step to Array size')
            elif not isinstance(size.start, int) or not isinstance(size.stop, int):
                raise ValueError('Array min and max length must be integers')
            elif size.start < 0:
                raise ValueError(f'Array minimum size must not be negative, got {size.start}')
            elif size.stop < size.start:
                raise ValueError('Array maximum size must be greater than its minimum size')
            size_min, size_max = size.start, size.stop
        else:
            raise TypeError(f'Expected int or a slice as array size, got {get_type_name(size)}')
        
        if not issubclass(get_as_type(serializer), Serializer):
            raise TypeError(f'Array element type must be a Serializer')

        if serializer._heracles_hidden_() and size_min != size_max:
            raise ValueError(f'Array of {get_type_name(serializer)} cannot be variable size')

        serializer = get_as_value(serializer)
        return type(get_type_name(cls), (cls,), {
            SerializerMeta.METAATTR: SerializerMetadata(
                serializer._heracles_bytesize_() * size_min),
            '_array_size_min': size_min,
            '_array_size_max': size_max,
            '_serializer': serializer
        })

    def __repr__(cls) -> str:
        if cls._heracles_vst_():
            size = f'{cls._array_size_min}:{cls._array_size_max}'
        else:
            size = f'{cls._array_size_min}'
        return f'<array <{cls._serializer}> [{size}]>'


class Array(Serializer, metaclass=ArrayMeta):
    _array_size_min = _array_size_max = 0

    def __init__(self, value: Sequence=(), *args, **kwargs):
        return super().__init__(value, *args, **kwargs)
    
    @classmethod
    def _heracles_hidden_(cls) -> bool:
        return cls._serializer._heracles_hidden_()

    @classmethod
    def _heracles_vst_(cls):
        return cls._array_size_min != cls._array_size_max

    @instanceoverride
    def _heracles_bytesize_(self, value: Optional[TypeUnion['Array', Sequence]] = None):
        value = self._heracles_validate_(value)
        return max(self._array_size_min, len(value)) * self._serializer._heracles_bytesize_()

    def _heracles_validate_(self, value: Optional[TypeUnion['Array', Sequence]] = None) -> Sequence:
        value = self._get_serializer_value(value)
        if len(value) > self._array_size_max:
            raise ValueError('Assigned value size exceeds array size')

        for i in value:
            self._serializer._heracles_validate_(i)
        return value

    def serialize_value(self, value: TypeUnion['Array', Sequence], settings: Dict[str, Any] = None) -> bytes:
        if value_or_default(settings, {}).get('validate_on_serialize'):
            value = self._heracles_validate_(value)
        else:
            value = self._get_serializer_value(value)

        serialized = bytearray()
        for v in value:
            serialized.extend(self._serializer.serialize_value(v, settings))
        remaining_elements = (self._heracles_bytesize_(value) - len(serialized)) // self._serializer._heracles_bytesize_()
        for _ in range(remaining_elements):
            serialized.extend(self._serializer.serialize())

        return bytes(serialized)

    def deserialize(self, raw_data: ByteString, settings: Dict[str, Any] = None) -> Sequence:
        min_size = self._array_size_min * self._serializer._heracles_bytesize_()
        max_size = self._array_size_max * self._serializer._heracles_bytesize_()

        if not min_size <= len(raw_data) <= max_size:
            raise ValueError(f'Raw data size ({len(raw_data)}) is not in the expected range ({min_size}, {max_size})')
        
        if len(raw_data) % self._serializer._heracles_bytesize_() != 0:
            raise ValueError('Raw data size isn\'t divisible by array element size')

        values_iterator = (
            self._serializer.deserialize(chunk, settings)
            for chunk in iter_chunks(raw_data, self._serializer._heracles_bytesize_()))

        # Try to guess the best representation of the array for the user by inspecting
        # the type of the initial value, if exists, or of the underlying serializer
        # otherwise, falling back to the default representation if we couldn't guess.
        check_value = self.value if self.value != () else self._serializer.value
        if isinstance(check_value, bytes):
            return b''.join(values_iterator)
        elif isinstance(check_value, str):
            # This is a C-string, so strip NUL chars from the end
            return ''.join(values_iterator).rstrip('\x00')
        else:
            return type(self.value)(values_iterator)

    def _heracles_render_(self, value: Optional[TypeUnion['Array', Sequence]] = None) -> str:
        def as_int(v) -> int:
            return ord(v) if isinstance(v, (bytes, str)) else int(v)

        value = self._heracles_validate_(value)
        if self._heracles_vst_():
            size = f'{self._array_size_min}:{self._array_size_max}'
        else:
            size = f'{self._array_size_min}'

        # Try to guess the best representation of the array for the user by inspecting
        # the type of the initial value, if exists, or of the underlying serializer
        # otherwise, falling back to the default representation if we couldn't guess.
        check_value = self.value if self.value != () else self._serializer.value
        if isinstance(check_value, bytes):
            result = repr(b''.join(chr(as_int(v)).encode('ascii') for v in value))
        elif isinstance(check_value, str):
            # This is a C-string, so strip NUL chars from the end
            result = repr(''.join(chr(as_int(v)) for v in value).rstrip('\x00'))
        else:
            result = '{{{}}}'.format(', '.join(self._serializer._heracles_render_(v) for v in value))

        return f'{self._serializer}[{size}] {result}'
    
    def _heracles_compare_(self, other: TypeUnion['Array', Sequence], value: Optional[TypeUnion['Array', Sequence]] = None) -> bool:
        value = self._get_serializer_value(value)
        if other is None or max(len(other), len(value)) > self._array_size_max:
            return False

        return all(a == b for a, b in itertools.zip_longest(
            value, other, fillvalue=self._serializer))

    def __len__(self) -> int:
        return max(self._array_size_min, len(self.value))

    def __getitem__(self, idx):
        # TODO: slice?
        if idx < 0:
            idx = len(self) - idx
        if not 0 <= idx < self._array_size_max:
            raise IndexError('Array index out of range')
        try:
            return self._serializer._get_serializer_value(self.value[idx])
        except IndexError:
            return copy.deepcopy(self._serializer.value)

    def __iter__(self) -> Iterator:
        return (self[i] for i in range(len(self)))
