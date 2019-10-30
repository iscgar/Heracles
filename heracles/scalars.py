import sys
import struct
from typing import Any, ByteString, Dict, Mapping, Optional, Sequence, Union as TypeUnion

from .base import Endianness, Serializer, SerializerMeta, SerializerMetadata
from .validators import IntRangeValidator, FloatValidator, AsciiCharValidator
from ._utils import chain, type_name, is_strict_subclass, func_params, ParameterKind, strictclassproperty, strictproperty

__all__ = [
    'Scalar', 'PadByte', 'char', 'u8', 'i8', 'u16', 'i16', 'u32', 'i32', 'u64', 'i64', 'f32', 'f64',
    'uint8_t', 'int8_t', 'uint16_t', 'int16_t', 'uint32_t', 'int32_t', 'uint64_t', 'int64_t',
    'u8_le', 'i8_le', 'u16_le', 'i16_le', 'u32_le', 'i32_le', 'u64_le', 'i64_le', 'f32_le', 'f64_le',
    'u8_be', 'i8_be', 'u16_be', 'i16_be', 'u32_be', 'i32_be', 'u64_be', 'i64_be', 'f32_be', 'f64_be']


class ScalarMetadata(SerializerMetadata):
    __slots__ = ('endianness', 'fmt', 'fmt_spec', 'validator')
    _FORMATTERS_INFO = {
        'c': (1, AsciiCharValidator()),
        'B': (1, IntRangeValidator(0, 255)),
        'b': (1, IntRangeValidator(-128, 127)),
        'H': (2, IntRangeValidator(0, 65535)),
        'h': (2, IntRangeValidator(-32768, 32767)),
        'I': (4, IntRangeValidator(0, 4294967295)),
        'i': (4, IntRangeValidator(-2147483648, 2147483647)),
        'Q': (8, IntRangeValidator(0, 18446744073709551615)),
        'q': (8, IntRangeValidator(-9223372036854775808, 9223372036854775807)),
        'f': (4, FloatValidator(32)),
        'd': (8, FloatValidator(64)),
    }

    def __init__(self, *, endianness: Endianness, fmt: str):
        if not isinstance(endianness, Endianness):
            raise TypeError(f'Expected Endianness, got {type_name(endianness)}')
        if not fmt in self._FORMATTERS_INFO:
            raise ValueError(f'Unsupported scalar format: {fmt}')
        size, validator = self._FORMATTERS_INFO[fmt]
        self.endianness = endianness
        self.fmt = fmt
        self.fmt_spec = f'{endianness.value}{fmt}'
        self.validator = validator
        return super().__init__(size)


class ScalarMeta(SerializerMeta):
    _SCALAR_ARGS = tuple(
        p.name for p in func_params(ScalarMetadata.__init__, ParameterKind.KEYWORD_ONLY))

    def __new__(cls, name: str, bases: Sequence, classdict: Mapping[str, Any], **kwargs):
        if not hasattr(sys.modules[__name__], 'Scalar'):
            # Don't create metadata for Scalar itself
            return super().__new__(cls, name, bases, classdict, **kwargs)

        args = {}
        # Look for required arguments in base classes
        for b in (b for b in bases if issubclass(b, Serializer)):
            if not issubclass(b, Scalar):
                raise TypeError('Cannot inherit from non-Scalar serializer')
            elif b is Scalar:
                continue # Scalar itself has no metadata
            if args:
                raise TypeError('Cannot inherit from more than one Scalar base')
            meta = b.__metadata__
            for arg in cls._SCALAR_ARGS:
                args[arg] = getattr(meta, arg)
        # Override with keyword arguments, if any
        for k in cls._SCALAR_ARGS:
            if k in kwargs:
                args[k] = kwargs.pop(k)
        return super().__new__(
            cls, name, bases, classdict, metadata=ScalarMetadata(**args), **kwargs)

    @strictproperty
    def __iswrapper__(cls) -> bool:
        return True


class Scalar(Serializer, metaclass=ScalarMeta):
    def __init__(self, value: TypeUnion[int, float] = 0, *args, **kwargs):
        return super().__init__(value, *args, validator=chain(
            self.__metadata__.validator, kwargs.pop('validator', None)), **kwargs)

    def __int__(self) -> int:
        return int(self.value)

    def __float__(self) -> float:
        return float(self.value)

    def serialize_value(self, value: TypeUnion['Scalar', int, float], settings: Optional[Dict[str, Any]] = None) -> bytes:
        value = self._heracles_validate_(value)
        return struct.pack(self.__metadata__.fmt_spec, value)

    def deserialize(self, raw_data: ByteString, settings: Optional[Dict[str, Any]] = None) -> TypeUnion[int, float, bytes]:
        value = struct.unpack(self.__metadata__.fmt_spec, raw_data)[0]
        return self._heracles_validate_(value)


# Specialization of u8 to silently accept `bytes` values
class u8(Scalar, endianness=Endianness.native, fmt='B'):
    def _get_serializer_value(self, value: Optional[TypeUnion['u8', int, bytes]] = None):
        value = super()._get_serializer_value(value)
        if isinstance(value, bytes):
            return value[0]
        return value

    def deserialize(self, raw_data: ByteString, settings: Optional[Dict[str, Any]] = None):
        value = super().deserialize(raw_data, settings)
        if isinstance(self.value, bytes):
            return bytes((value,))
        return value


# Rest of native scalar types
class i8(Scalar, endianness=Endianness.native, fmt='b'): pass
class u16(Scalar, endianness=Endianness.native, fmt='H'): pass
class i16(Scalar, endianness=Endianness.native, fmt='h'): pass
class u32(Scalar, endianness=Endianness.native, fmt='I'): pass
class i32(Scalar, endianness=Endianness.native, fmt='i'): pass
class u64(Scalar, endianness=Endianness.native, fmt='Q'): pass
class i64(Scalar, endianness=Endianness.native, fmt='q'): pass
class f32(Scalar, endianness=Endianness.native, fmt='f'): pass
class f64(Scalar, endianness=Endianness.native, fmt='d'): pass

# stdint.h aliases of native scalar types
uint8_t = u8
int8_t = i8
uint16_t = u16
int16_t = i16
uint32_t = u32
int32_t = i32
uint64_t = u64
int64_t = i64

# Big endian scalar types
class u8_be(u8, endianness=Endianness.big): pass
class i8_be(Scalar, endianness=Endianness.big, fmt='b'): pass
class u16_be(Scalar, endianness=Endianness.big, fmt='H'): pass
class i16_be(Scalar, endianness=Endianness.big, fmt='h'): pass
class u32_be(Scalar, endianness=Endianness.big, fmt='I'): pass
class i32_be(Scalar, endianness=Endianness.big, fmt='i'): pass
class u64_be(Scalar, endianness=Endianness.big, fmt='Q'): pass
class i64_be(Scalar, endianness=Endianness.big, fmt='q'): pass
class f32_be(Scalar, endianness=Endianness.big, fmt='f'): pass
class f64_be(Scalar, endianness=Endianness.big, fmt='d'): pass

# Little endian scalar types
class u8_le(u8, endianness=Endianness.little): pass
class i8_le(Scalar, endianness=Endianness.little, fmt='b'): pass
class u16_le(Scalar, endianness=Endianness.little, fmt='H'): pass
class i16_le(Scalar, endianness=Endianness.little, fmt='h'): pass
class u32_le(Scalar, endianness=Endianness.little, fmt='I'): pass
class i32_le(Scalar, endianness=Endianness.little, fmt='i'): pass
class u64_le(Scalar, endianness=Endianness.little, fmt='Q'): pass
class i64_le(Scalar, endianness=Endianness.little, fmt='q'): pass
class f32_le(Scalar, endianness=Endianness.little, fmt='f'): pass
class f64_le(Scalar, endianness=Endianness.little, fmt='d'): pass


class char(Scalar, endianness=Endianness.native, fmt='c'):
    def __init__(self, value: TypeUnion[str, bytes] = '\x00', *args, **kwargs):
        return super().__init__(value, *args, **kwargs)

    def serialize_value(self, value: TypeUnion[str, bytes], settings: Optional[Dict[str, Any]] = None) -> bytes:
        if isinstance(value, str):
            value = value.encode('ascii')
        return super().serialize_value(value, settings)

    def deserialize(self, raw_data: ByteString, settings: Optional[Dict[str, Any]] = None) -> str:
        return super().deserialize(raw_data, settings).decode('ascii')

    def __int__(self) -> int:
        return ord(self.value)

    def __float__(self) -> float:
        return float(int(self))


class PadByte(u8):
    @strictclassproperty
    def __ishidden__(cls) -> bool:
        return True

    def _heracles_validate_(self, value: Optional[TypeUnion[int, bytes]] = None) -> int:
        value = super()._heracles_validate_(value)
        if value != self._get_serializer_value():
            raise ValueError(f'Expected padding value {self.value}, got {value}')
        return value

    def deserialize(self, raw_data: ByteString, settings: Optional[Dict[str, Any]] = None) -> bytes:
        return super().deserialize(raw_data, settings) and b''
