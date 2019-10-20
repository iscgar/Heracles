import struct
from typing import Any, ByteString, Dict, Optional, Type, Union as TypeUnion

from .base import Endianness, Serializer, SerializerMeta, SerializerMetadata
from .validators import Validator, PredicateValidator, IntRangeValidator, FloatValidator
from .utils import value_or_default

__all__ = [
    'Scalar', 'char', 'u8', 'i8', 'u16', 'i16', 'u32', 'i32', 'u64', 'i64', 'f32', 'f64',
    'u8_le', 'i8_le', 'u16_le', 'i16_le', 'u32_le', 'i32_le', 'u64_le', 'i64_le', 'f32_le', 'f64_le',
    'u8_be', 'i8_be', 'u16_be', 'i16_be', 'u32_be', 'i32_be', 'u64_be', 'i64_be', 'f32_be', 'f64_be']


class Scalar(Serializer):
    def __init__(self, value: TypeUnion[int, float] = 0, *args, **kwargs):
        super().__init__(value, *args, **kwargs)

    def __int__(self) -> int:
        return int(self.value)

    def __float__(self) -> float:
        return float(self.value)

    def _heracles_validate_(self, value: Optional[TypeUnion['Scalar', int, float]] = None) -> TypeUnion[int, float]:
        value = self._get_serializer_value(value)
        self._heracles_metadata_().validator(value)
        return super()._heracles_validate_(value)

    def serialize_value(self, value: TypeUnion['Scalar', int, float], settings: Optional[Dict[str, Any]] = None) -> bytes:
        value = self._get_serializer_value(value)
        if value_or_default(settings, {}).get('validate_on_serialize'):
            self._heracles_validate_(value)
        return struct.pack(self._heracles_metadata_().fmt, value)

    def deserialize(self, raw_data: ByteString, settings: Optional[Dict[str, Any]] = None) -> Any:
        value = struct.unpack(self._heracles_metadata_().fmt, raw_data)[0]
        self._heracles_validate_(value)
        return value


def _scalar_type(name: str, size: int, endianness: Endianness, fmt: str, validator: Validator) -> Type[Scalar]:
    return type(name, (Scalar,), {
        SerializerMeta.METAATTR: SerializerMetadata(
            size, fmt=f'{endianness.value}{fmt}', validator=validator)})


def _char_type() -> Type[Scalar]:
    char = _scalar_type('char', 1, Endianness.native, 'c', PredicateValidator(
        lambda v: isinstance(v, (str, bytes)) and len(v) == 1 and 0 <= ord(v) < 256))
    __class__ = char

    def convert_to_chr(value: TypeUnion[str, bytes]) -> str:
        if isinstance(value, bytes):
            value = value.decode('ascii')
        return value

    def convert_from_chr(value: TypeUnion[str, bytes]) -> bytes:
        if isinstance(value, str):
            value = value.encode('ascii')
        return value

    def init(self, value: TypeUnion[str, bytes] = '\x00', *args, **kwargs):
        super(char, self).__init__(value, *args, **kwargs)

    def serialize_value(self, value: TypeUnion[str, bytes], settings: Optional[Dict[str, Any]] = None) -> bytes:
        return super(char, self).serialize_value(convert_from_chr(value), settings)

    def deserialize(self, raw_data: ByteString, settings: Optional[Dict[str, Any]] = None) -> str:
        return convert_to_chr(super(char, self).deserialize(raw_data, settings))

    char.__init__ = init
    char.__int__ = lambda self: ord(self.value)
    char.__float__ = lambda self: float(int(self.value))
    char.serialize_value = serialize_value
    char.deserialize = deserialize
    return char


def _u8_type(name: str, endianness: Endianness) -> Type[Scalar]:
    typ = _scalar_type(name, 1, endianness, 'B', IntRangeValidator(0, 255))
    __class__ = typ

    def convert(value):
        # Silently convert from byte string to value for u8*
        if isinstance(value, bytes) and len(value) == typ._heracles_bytesize_():
            return ord(value)
        return value

    def init(self, value: TypeUnion[int, bytes] = 0, *args, **kwargs):
        super(typ, self).__init__(convert(value), *args, **kwargs)

    def _heracles_validate_(self, value: Optional[TypeUnion[typ, int, bytes]] = None) -> int:
        return super(typ, self)._heracles_validate_(convert(value))

    def serialize_value(self, value: TypeUnion[typ, int, bytes], settings: Dict[str, Any] = None) -> bytes:
        return super(typ, self).serialize_value(convert(value), settings)

    typ.__init__ = init
    typ._heracles_validate_ = _heracles_validate_
    typ.serialize_value = serialize_value
    return typ


char = _char_type()

u8 = _u8_type('u8', Endianness.native)
i8 = _scalar_type('i8', 1, Endianness.native, 'b', IntRangeValidator(-128, 127))
u16 = _scalar_type('u16', 2, Endianness.native, 'H', IntRangeValidator(0, 65535))
i16 = _scalar_type('i16', 2, Endianness.native, 'h', IntRangeValidator(-32768, 32767))
u32 = _scalar_type('u32', 4, Endianness.native, 'I', IntRangeValidator(0, 4294967295))
i32 = _scalar_type('i32', 4, Endianness.native, 'i', IntRangeValidator(-2147483648, 2147483647))
u64 = _scalar_type('u64', 8, Endianness.native, 'Q', IntRangeValidator(0, 18446744073709551615))
i64 = _scalar_type('i64', 8, Endianness.native, 'q', IntRangeValidator(-9223372036854775808, 9223372036854775807))
f32 = _scalar_type('f32', 4, Endianness.native, 'f', FloatValidator(32))
f64 = _scalar_type('f64', 8, Endianness.native, 'd', FloatValidator(64))

u8_be = _u8_type('u8_be', Endianness.big)
i8_be = _scalar_type('i8_be', 1, Endianness.big, 'b', IntRangeValidator(-128, 127))
u16_be = _scalar_type('u16_be', 2, Endianness.big, 'H', IntRangeValidator(0, 65535))
i16_be = _scalar_type('i16_be', 2, Endianness.big, 'h', IntRangeValidator(-32768, 32767))
u32_be = _scalar_type('u32_be', 4, Endianness.big, 'I', IntRangeValidator(0, 4294967295))
i32_be = _scalar_type('i32_be', 4, Endianness.big, 'i', IntRangeValidator(-2147483648, 2147483647))
u64_be = _scalar_type('u64_be', 8, Endianness.big, 'Q', IntRangeValidator(0, 18446744073709551615))
i64_be = _scalar_type('i64_be', 8, Endianness.big, 'q', IntRangeValidator(-9223372036854775808, 9223372036854775807))
f32_be = _scalar_type('f32_be', 4, Endianness.big, 'f', FloatValidator(32))
f64_be = _scalar_type('f64_be', 8, Endianness.big, 'd', FloatValidator(64))

u8_le = _u8_type('u8_le', Endianness.little)
i8_le = _scalar_type('i8_le', 1, Endianness.little, 'b', IntRangeValidator(-128, 127))
u16_le = _scalar_type('u16_le', 2, Endianness.little, 'H', IntRangeValidator(0, 65535))
i16_le = _scalar_type('i16_le', 2, Endianness.little, 'h', IntRangeValidator(-32768, 32767))
u32_le = _scalar_type('u32_le', 4, Endianness.little, 'I', IntRangeValidator(0, 4294967295))
i32_le = _scalar_type('i32_le', 4, Endianness.little, 'i', IntRangeValidator(-2147483648, 2147483647))
u64_le = _scalar_type('u64_le', 8, Endianness.little, 'Q', IntRangeValidator(0, 18446744073709551615))
i64_le = _scalar_type('i64_le', 8, Endianness.little, 'q', IntRangeValidator(-9223372036854775808, 9223372036854775807))
f32_le = _scalar_type('f32_le', 4, Endianness.little, 'f', FloatValidator(32))
f64_le = _scalar_type('f64_le', 8, Endianness.little, 'd', FloatValidator(64))
