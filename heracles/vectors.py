import itertools
import typing

from .base import Serializer, SerializerMeta, SerializerMetadata
from .scalars import u8
from .utils import get_type_name, get_as_type, get_as_value, value_or_default, iter_chunks
from .validators import ExactValueValidator


__all__ = ['Array', 'VariableArray', 'Padding']


class _Array(Serializer):
    def __init__(self, value: typing.Sequence=(), *args, **kwargs):
        return super().__init__(value, *args, **kwargs)

    def _heracles_validate_(self, value: typing.Optional[typing.Union['_Array', typing.Sequence]]=None) -> typing.Sequence:
        value = self._get_serializer_value(value)
        if len(value) > len(self):
            raise ValueError('Assigned value size exceeds array size')

        for i in value:
            self.serializer._heracles_validate_(i)
        return value

    def serialize_value(self, value: typing.Union['_Array', typing.Sequence], settings: typing.Dict[str, typing.Any]=None) -> bytes:
        value = self._get_serializer_value(value)
        if value_or_default(settings, {}).get('_heracles_validate__on_serialize'):
            self._heracles_validate_(value)

        serialized = b''.join(self.serializer.serialize_value(v, settings) for v in value)
        if len(serialized) < self._heracles_bytesize_(value):
            serialized += b''.join(self.serializer.serialize() for _ in range(len(self) - len(value)))

        return serialized

    def deserialize(self, raw_data: typing.ByteString, settings: typing.Dict[str, typing.Any]=None) -> typing.Sequence:
        if len(raw_data) != self._heracles_bytesize_():
            raise ValueError('Raw data is not in the correct length')
        return self._deserialize(raw_data, settings)

    def _deserialize(self, raw_data: typing.ByteString, settings: typing.Dict[str, typing.Any]=None) -> typing.Sequence:
        if len(raw_data) % self.serializer._heracles_bytesize_() != 0:
            raise ValueError('Raw data size isn\'t divisible by array element size')

        values_iterator = (
            self.serializer.deserialize(chunk, settings)
            for chunk in iter_chunks(raw_data, self.serializer._heracles_bytesize_()))

        # Try to guess the best representation of the array for the user by inspecting
        # the type of the initial value, if exists, or of the underlying serializer
        # otherwise, falling back to the default representation if we couldn't guess.
        check_value = self.value if self.value != () else self.serializer.value
        if isinstance(check_value, bytes):
            return b''.join(values_iterator)
        elif isinstance(check_value, str):
            # This is a C-string, so strip NUL chars from the end
            return ''.join(values_iterator).rstrip('\x00')
        else:
            return type(self.value)(values_iterator)

    def _heracles_render_(self, value: typing.Optional[typing.Union['_Array', typing.Sequence]]=None) -> str:
        value = self._heracles_validate_(value)
        return f'{get_type_name(self)}({len(value)}, {self._repr_array_value(value)})'
    
    def _heracles_compare_(self, other: typing.Union['_Array', typing.Sequence], value: typing.Optional[typing.Union['_Array', typing.Sequence]]=None) -> bool:
        value = self._get_serializer_value(value)
        if max(len(other), len(value)) > len(self):
            return False

        return all(a == b for a, b in itertools.zip_longest(
            value, other, fillvalue=self.serializer))

    def _repr_array_value(self, value: typing.Optional[typing.Union['_Array', typing.Sequence]]=None) -> str:
        def as_int(v) -> int:
            return ord(v) if isinstance(v, (bytes, str)) else int(v)

        value = self._get_serializer_value(value)

        # Try to guess the best representation of the array for the user by inspecting
        # the type of the initial value, if exists, or of the underlying serializer
        # otherwise, falling back to the default representation if we couldn't guess.
        check_value = self.value if self.value != () else self.serializer.value
        if isinstance(check_value, bytes):
            return repr(b''.join(chr(as_int(v)).encode('ascii') for v in value))
        elif isinstance(check_value, str):
            # This is a C-string, so strip NUL chars from the end
            return repr(''.join(chr(as_int(v)) for v in value).rstrip('\x00'))
        else:
            return '{{{}}}'.format(', '.join(repr(v) for v in value))

    @classmethod
    def __len__(cls) -> int:
        # TODO: this call is broken for variable array
        return cls._heracles_bytesize_() // cls.serializer._heracles_bytesize_()

    def __iter__(self):
        for v in self.value:
            yield self.serializer._get_serializer_value(v)

        for _ in range(len(self.value), len(type(self))):
            yield self.serializer.value


class _Padding(_Array):
    def __init__(self, *args, **kwargs):
        return super().__init__(b'', *args, **kwargs)

    @classmethod
    def _hidden_(cls) -> bool:
        return True

    def deserialize(self, raw_data: typing.ByteString, settings: typing.Dict[str, typing.Any]=None):
        super().deserialize(raw_data, settings)
        return b''

    def _heracles_render_(self, value=None) -> str:
        return f'{get_type_name(self)}({len(self)}, {self.serializer.serialize()})'


class _VariableArray(_Array):
    @classmethod
    def _heracles_vst_(cls) -> bool:
        return True
    
    def __len__(self) -> int:
        return self._heracles_bytesize_() // self.serializer._heracles_bytesize_()

    def _heracles_bytesize_(self, value: typing.Optional[typing.Union['_VariableArray', typing.Sequence]]=None) -> int:
        value = self._heracles_validate_(self._get_serializer_value(value))
        return max(len(value), super().__len__()) * self.serializer._heracles_bytesize_()

    def deserialize(self, raw_data: typing.ByteString, settings=None):
        if len(raw_data) > self.max_length * len(self.serializer):
            raise ValueError('Raw data is too long for variable length array')
        elif len(raw_data) < self.min_length * len(self.serializer):
            raise ValueError('Raw data is too short for variable length array')
        return self._deserialize(raw_data, settings)

    def _heracles_compare_(self, other: '_VariableArray', value: typing.Optional[typing.Union['_VariableArray', typing.Sequence]]=None) -> bool:
        value = self._get_serializer_value(value)
        if other is None or self._get_serializer_value(other) != len(value):
            return False

        return all(a == b for a, b in itertools.izip_longest(
            self, other, fillvalue=self.serializer))

    def _heracles_render_(self, value: typing.Optional[typing.Union['_VariableArray', typing.Sequence]]=None) -> str:
        return f'{get_type_name(self)}([{self.min_length}:{self.max_length}], {self._repr_array_value(value)} ({len(value)}))'

    def _heracles_validate_(self, value: typing.Optional[typing.Union['_VariableArray', typing.Sequence]]=None) -> typing.Sequence:
        value = self._get_serializer_value(value)
        if len(value) > self.max_length:
            raise ValueError(
                f'Data size ({len(value)}) exceeds the size of VLA [{self.min_length}, {self.max_length}]')

        for i in value:
            self.serializer._heracles_validate_(i)
        return value


def _array(cls, name: str, size: int, items_type: typing.Type[Serializer]) -> typing.Type[_Array]:
    if not issubclass(get_as_type(items_type), Serializer):
        raise TypeError('Array item type should be a Serializer')

    serializer = get_as_value(items_type)

    if serializer._heracles_vst_():
        raise TypeError('Array item type must not be variable length')

    return type(name, (cls,), {
            SerializerMeta.METAATTR: SerializerMetadata(
                size * serializer._heracles_bytesize_()),
            'serializer': serializer,
            })


def Array(size: int, items_type=u8) -> typing.Type[_Array]:
    return _array(_Array, 'Array', size, items_type)


def VariableArray(min_length: int, max_length: int, items_type: typing.Type[Serializer]=u8) -> typing.Type[_VariableArray]:
    if not isinstance(min_length, int) or not isinstance(max_length, int):
        raise ValueError('VariableArray min and max length must be integers')

    if not 0 <= min_length < max_length:
        raise ValueError('VariableArray min length must be smaller than max length')

    result = _array(_VariableArray, 'VariableArray', min_length, items_type)
    result.min_length = min_length
    result.max_length = max_length
    return result


def Padding(size: int, pad_value: typing.Union[int, bytes]=0) -> typing.Type[_Padding]:
    return _array(_Padding, 'Padding', size, u8(
        pad_value, validator=ExactValueValidator(pad_value)))
