import sys
import itertools
from typing import Any, Dict, ByteString, Optional, Sequence, Type, Union as TypeUnion

from .base import Serializer, SerializerMeta, SerializerMetadata
from .scalars import u8
from .utils import get_type_name, get_as_type, get_as_value, value_or_default, iter_chunks
from .validators import ExactValueValidator


__all__ = ['Array', 'Padding']


class ArrayMeta(SerializerMeta):
    def __call__(cls, *args, **kwargs):
        is_array_type = (
            issubclass(cls, Array) and 
            getattr(cls, '__module__', None) == __name__ and
            getattr(sys.modules[__name__], get_type_name(cls), None) == cls)

        if is_array_type and not kwargs and 1 <= len(args) <= 2:
            # Default serializer is u8
            if len(args) == 2:
                size, serializer = args
            else:
                size, serializer = args[0], u8

            if isinstance(size, (int, slice)) and issubclass(get_as_type(serializer), Serializer):
                if isinstance(size, slice):
                    if size.step is not None:
                        raise ValueError('Cannot supply step as array size')
                    if not isinstance(size.start, int) or not isinstance(size.stop, int):
                        raise ValueError('Array min and max length must be integers')
                    if size.start == size.stop:
                        size = size.start

                if isinstance(size, int):
                    size_min = size_max = size
                else:
                    size_min, size_max = size.start, size.stop
                
                serializer = get_as_value(serializer)
                return type(get_type_name(cls), (cls,), {
                    SerializerMeta.METAATTR: SerializerMetadata(
                        serializer._heracles_bytesize_() * size_min),
                    '_array_size_min': size_min,
                    '_array_size_max': size_max,
                    '_serializer': serializer
                })

        return super().__call__(*args, **kwargs)

    def __repr__(cls) -> str:
        if cls._heracles_vst_():
            size = f'{cls._array_size_min}:{cls._array_size_max}'
        else:
            size = f'{cls._array_size_min}'
        return f'<array {get_type_name(cls._serializer)}[{size}]>'


class Array(Serializer, metaclass=ArrayMeta):
    _array_size_min = _array_size_max = 0

    def __init__(self, value: Sequence=(), *args, **kwargs):
        return super().__init__(value, *args, **kwargs)
    
    @classmethod
    def _heracles_vst_(cls):
        return cls._array_size_min != cls._array_size_max

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

        serialized = b''.join(self._serializer.serialize_value(v, settings) for v in value)
        if len(serialized) < self._heracles_bytesize_(value):
            serialized += b''.join(self._serializer.serialize() for _ in range(len(self) - len(value)))

        return serialized

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
            result = '{{{}}}'.format(', '.join(repr(v) for v in value))

        return f'{get_type_name(self)}({get_type_name(self._serializer)}[{size}]) {result}'
    
    def _heracles_compare_(self, other: TypeUnion['Array', Sequence], value: Optional[TypeUnion['Array', Sequence]] = None) -> bool:
        value = self._get_serializer_value(value)
        if other is None or max(len(other), len(value)) > self._array_size_max:
            return False

        return all(a == b for a, b in itertools.zip_longest(
            value, other, fillvalue=self._serializer))

    def __len__(self) -> int:
        return max(self._array_size_min, len(self.value))

    def __iter__(self):
        for v in self.value:
            yield self._serializer._get_serializer_value(v)

        for _ in range(len(self.value), len(self)):
            yield self._serializer.value


class PaddingMeta(ArrayMeta):
    def __call__(cls, *args, **kwargs):
        if cls is Padding and not kwargs and 1 <= len(args) <= 2:
            # Default pad value is b'\x00'
            if len(args) == 2:
                size, pad_value = args
            else:
                size, pad_value = args[0], b'\x00'

            if isinstance(size, int):
                args = [size, u8(pad_value, validator=ExactValueValidator(
                    u8(pad_value).value))]

        return super().__call__(*args, **kwargs)

    def __repr__(cls) -> str:
        return f'<padding {get_type_name(cls._serializer)}[{cls._array_min_size}] ({cls._serializer.serialize()})>'


class Padding(Array, metaclass=PaddingMeta):
    def __init__(self, *args, **kwargs):
        return super().__init__(b'', *args, **kwargs)

    @classmethod
    def _hidden_(cls) -> bool:
        return True

    def deserialize(self, raw_data: ByteString, settings: Dict[str, Any]=None):
        super().deserialize(raw_data, settings)
        return b''

    def _heracles_render_(self, value=None) -> str:
        name = get_type_name(self)
        size = len(self)
        val = self._serializer.serialize()
        return f'{name}({size}, {val})'
