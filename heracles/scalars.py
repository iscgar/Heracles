import struct
import typing

from .base import Serializer, SerializerMeta, SerializerMetadata
from .validators import Validator, PredicateValidator, IntRangeValidator, FloatValidator
from .utils import value_or_default

__all__ = [
    'Scalar', 'char', 'u8', 'i8', 'u16', 'i16', 'u32', 'i32', 'u64', 'i64', 'f32', 'f64',
    'u8_le', 'i8_le', 'u16_le', 'i16_le', 'u32_le', 'i32_le', 'u64_le', 'i64_le', 'f32_le', 'f64_le',
    'u8_be', 'i8_be', 'u16_be', 'i16_be', 'u32_be', 'i32_be', 'u64_be', 'i64_be', 'f32_be', 'f64_be']


class Scalar(Serializer):
    def __init__(self, value=0, *args, **kwargs):
        super().__init__(value, *args, **kwargs)

    def __int__(self) -> int:
        return int(self.value)

    def __float__(self) -> float:
        return float(self.value)

    def validate(self, value: typing.Union['Scalar', int, float]=None) -> typing.Union[int, float]:
        value = self.get_serializer_value(value)
        self.metadata().validator(value)
        return super().validate(value)

    def serialize_value(self, value, settings: typing.Dict[str, typing.Any]=None) -> bytes:
        if value_or_default(settings, {}).get('validate_on_serialize'):
            self.validate()
        return struct.pack(self.metadata().fmt, value)

    def deserialize(self, raw_data: typing.ByteString, settings: typing.Dict[str, typing.Any]=None):
        value = struct.unpack(self.metadata().fmt, raw_data)[0]
        self.validate(value)
        return value


def _scalar_type(name: str, size: int, fmt: str, validator: Validator) -> typing.Type[Scalar]:
    return type(name, (Scalar,), {
        SerializerMeta.METAATTR: SerializerMetadata(
            size, fmt=fmt, validator=validator)})


def _char_type() -> typing.Type[Scalar]:
    char = _scalar_type('char', 1, '=c', PredicateValidator(
        lambda v: isinstance(v, (str, bytes)) and len(v) == 1 and 0 <= ord(v) < 256))
    __class__ = char

    def convert_to_chr(value):
        if isinstance(value, bytes):
            value = value.decode('ascii')
        return value

    def convert_from_chr(value):
        if isinstance(value, str):
            value = value.encode('ascii')
        return value

    def init(self, value='\x00', *args, **kwargs):
        super(char, self).__init__(value, *args, **kwargs)

    def serialize_value(self, value, settings=None) -> bytes:
        return super(char, self).serialize_value(convert_from_chr(value), settings)

    def deserialize(self, raw_data, settings=None) -> bytes:
        return convert_to_chr(super(char, self).deserialize(raw_data, settings))

    char.__init__ = init
    char.__int__ = lambda self: ord(self.value)
    char.__float__ = lambda self: float(int(self.value))
    char.serialize_value = serialize_value
    char.deserialize = deserialize
    return char


def _u8_type(name: str, endianness: str) -> typing.Type[Scalar]:
    typ = _scalar_type(name, 1, f'{endianness}B', IntRangeValidator(0, 255))
    __class__ = typ

    def convert(value):
        # Silently convert from byte string to value for u8*
        if isinstance(value, bytes) and len(value) == len(typ):
            return ord(value)
        return value

    def init(self, value: typing.Union[int, bytes]=0, *args, **kwargs):
        super(typ, self).__init__(convert(value), *args, **kwargs)

    def validate(self, value: typing.Optional[typing.Union[typ, int, bytes]]=None) -> int:
        return super(typ, self).validate(convert(value))

    def serialize_value(self, value: typing.Union[typ, int, bytes], settings: typing.Dict[str, typing.Any]=None) -> bytes:
        return super(typ, self).serialize_value(convert(value), settings)

    typ.__init__ = init
    typ.validate = validate
    typ.serialize_value = serialize_value
    return typ


char = _char_type()

u8 = _u8_type('u8', '=')
i8 = _scalar_type('i8', 1, '=b', IntRangeValidator(-128, 127))
u16 = _scalar_type('u16', 2, '=H', IntRangeValidator(0, 65535))
i16 = _scalar_type('i16', 2, '=h', IntRangeValidator(-32768, 32767))
u32 = _scalar_type('u32', 4, '=I', IntRangeValidator(0, 4294967295))
i32 = _scalar_type('i32', 4, '=i', IntRangeValidator(-2147483648, 2147483647))
u64 = _scalar_type('u64', 8, '=Q', IntRangeValidator(0, 18446744073709551615))
i64 = _scalar_type('i64', 8, '=q', IntRangeValidator(-9223372036854775808, 9223372036854775807))
f32 = _scalar_type('f32', 4, '=f', FloatValidator(32))
f64 = _scalar_type('f64', 8, '=d', FloatValidator(64))

u8_be = _u8_type('u8_be', '>')
i8_be = _scalar_type('i8_be', 1, '>b', IntRangeValidator(-128, 127))
u16_be = _scalar_type('u16_be', 2, '>H', IntRangeValidator(0, 65535))
i16_be = _scalar_type('i16_be', 2, '>h', IntRangeValidator(-32768, 32767))
u32_be = _scalar_type('u32_be', 4, '>I', IntRangeValidator(0, 4294967295))
i32_be = _scalar_type('i32_be', 4, '>i', IntRangeValidator(-2147483648, 2147483647))
u64_be = _scalar_type('u64_be', 8, '>Q', IntRangeValidator(0, 18446744073709551615))
i64_be = _scalar_type('i64_be', 8, '>q', IntRangeValidator(-9223372036854775808, 9223372036854775807))
f32_be = _scalar_type('f32_be', 4, '>f', FloatValidator(32))
f64_be = _scalar_type('f64_be', 8, '>d', FloatValidator(64))

u8_le = _u8_type('u8_le', '<')
i8_le = _scalar_type('i8_le', 1, '<b', IntRangeValidator(-128, 127))
u16_le = _scalar_type('u16_le', 2, '<H', IntRangeValidator(0, 65535))
i16_le = _scalar_type('i16_le', 2, '<h', IntRangeValidator(-32768, 32767))
u32_le = _scalar_type('u32_le', 4, '<I', IntRangeValidator(0, 4294967295))
i32_le = _scalar_type('i32_le', 4, '<i', IntRangeValidator(-2147483648, 2147483647))
u64_le = _scalar_type('u64_le', 8, '<Q', IntRangeValidator(0, 18446744073709551615))
i64_le = _scalar_type('i64_le', 8, '<q', IntRangeValidator(-9223372036854775808, 9223372036854775807))
f32_le = _scalar_type('f32_le', 4, '<f', FloatValidator(32))
f64_le = _scalar_type('f64_le', 8, '<d', FloatValidator(64))
