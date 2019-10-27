import sys
import struct
from typing import Any, ByteString, Dict, Optional, Sequence, Union as TypeUnion

from .base import Endianness, Serializer, SerializerMeta, SerializerMetadata
from .validators import IntRangeValidator, FloatValidator, AsciiCharValidator
from ._utils import chain, get_type_name, is_strict_subclass

__all__ = [
    'Scalar', 'PadByte', 'char', 'u8', 'i8', 'u16', 'i16', 'u32', 'i32', 'u64', 'i64', 'f32', 'f64',
    'uint8_t', 'int8_t', 'uint16_t', 'int16_t', 'uint32_t', 'int32_t', 'uint64_t', 'int64_t',
    'u8_le', 'i8_le', 'u16_le', 'i16_le', 'u32_le', 'i32_le', 'u64_le', 'i64_le', 'f32_le', 'f64_le',
    'u8_be', 'i8_be', 'u16_be', 'i16_be', 'u32_be', 'i32_be', 'u64_be', 'i64_be', 'f32_be', 'f64_be']


class ScalarMeta(SerializerMeta):
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
    _SCALAR_ARGS = ('endianness', 'fmt')

    def __new__(cls, name, bases, classdict, **kwargs):
        if hasattr(sys.modules[__name__], 'Scalar'):
            args = {}
            # Look for required arguments in base classes
            for b in (b for b in bases if is_strict_subclass(b, Scalar)):
                meta = b._heracles_metadata_()
                endianness, fmt = meta.fmt
                args['endianness'] = Endianness(endianness)
                args['fmt'] = fmt
            # Override with keyword arguments, if any
            for k in cls._SCALAR_ARGS:
                if k in kwargs:
                    args[k] = kwargs[k]
                    del kwargs[k]
            classdict[SerializerMeta.METAATTR] = cls.scalar_metadata(**args)
        return super().__new__(cls, name, bases, classdict, **kwargs)

    @classmethod
    def scalar_metadata(cls, *, endianness: Endianness, fmt: str) -> SerializerMetadata:
        if not isinstance(endianness, Endianness):
            raise TypeError(f'Expected Endianness, got {get_type_name(endianness)}')
        if not fmt in cls._FORMATTERS_INFO:
            raise ValueError(f'Unsupported scalar format: {fmt}')
        size, validator = cls._FORMATTERS_INFO[fmt]
        return SerializerMetadata(
            size, fmt=f'{endianness.value}{fmt}', validator=validator)


class Scalar(Serializer, metaclass=ScalarMeta):
    def __init__(self, value: TypeUnion[int, float] = 0, *args, **kwargs):
        kwargs['validator'] = tuple(
            chain(self._heracles_metadata_().validator, kwargs.get('validator')))
        super().__init__(value, *args, **kwargs)

    def __int__(self) -> int:
        return int(self.value)

    def __float__(self) -> float:
        return float(self.value)

    def serialize_value(self, value: TypeUnion['Scalar', int, float], settings: Optional[Dict[str, Any]] = None) -> bytes:
        value = self._heracles_validate_(value)
        return struct.pack(self._heracles_metadata_().fmt, value)

    def deserialize(self, raw_data: ByteString, settings: Optional[Dict[str, Any]] = None) -> TypeUnion[int, float, bytes]:
        value = struct.unpack(self._heracles_metadata_().fmt, raw_data)[0]
        return self._heracles_validate_(value)


# Specialization of u8 to silently accept `bytes` values
class u8(Scalar, endianness=Endianness.native, fmt='B'):
    def _get_serializer_value(self, value: Optional[TypeUnion['u8', int, bytes]] = None):
        value = super()._get_serializer_value(value)
        if isinstance(value, bytes):
            return value[0]
        return value

    def deserialize(self, raw_data, settings: Optional[Dict[str, Any]] = None):
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
        super().__init__(value, *args, **kwargs)

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
    @classmethod
    def _heracles_hidden_(cls) -> bool:
        return True

    def _heracles_validate_(self, value: Optional[TypeUnion[int, bytes]] = None) -> int:
        value = super()._heracles_validate_(value)
        if value != self._get_serializer_value():
            raise ValueError(f'Expected padding value {self.value}, got {value}')
        return value

    def deserialize(self, raw_data: ByteString, settings: Optional[Dict[str, Any]] = None) -> bytes:
        return super().deserialize(raw_data, settings) and b''
