import struct
from .base import Serializer, SerializerMeta, SerializerMetadata
from .validators import PredicateValidator, RangeValidator, FloatValidator
from .utils import value_or_default, get_type_name, mask


class Scalar(Serializer):
    def __init__(self, value=0, *args, **kwargs):
        super(Scalar, self).__init__(value, *args, **kwargs)

    def __int__(self):
        return int(self.value)

    def __float__(self):
        return float(self.value)

    def validate(self, value=None):
        value = self.get_serializer_value(value)
        self.metadata().validator(value)
        super(Scalar, self).validate(value)

    def serialize_value(self, value, settings=None) -> bytes:
        if value_or_default(settings, {}).get('validate_on_serialize'):
            self.validate()

        return struct.pack(self.metadata().fmt, value)

    def deserialize(self, raw_data, _=None):
        assert issubclass(type(self), Scalar), 'Cannot deserialize non-scalar types'
        value = struct.unpack(self.metadata().fmt, raw_data)[0]
        self.validate(value)
        return value


def _scalar_type(name, size, fmt, validator):
    return type(name, (Scalar,), {
        SerializerMeta.METAATTR: SerializerMetadata(
            name, size, fmt=fmt, validator=validator)})


def _char_type():
    char = _scalar_type('char', 1, '=c', PredicateValidator(lambda v: 0 <= ord(v) < 256))

    def init(self, value='\x00', *args, **kwargs):
        if isinstance(value, bytes):
            value = value.decode('ascii')
        elif isinstance(value, int):
            value = chr(value)
        super(char, self).__init__(value, *args, **kwargs)

    char.__init__ = init
    char.__int__ = lambda self: ord(self.value)
    char.__float__ = lambda self: float(int(self.value))
    return char


def _u8_type(name, fmt):
    typ = _scalar_type(name, 1, fmt, RangeValidator(0, 255))

    def convert(value):
        # Silently convert from byte string to value for u8*
        if isinstance(value, bytes) and len(value) == len(self):
            return ord(value)
        return value

    def init(self, value=0, *args, **kwargs):
        super(type(self), self).__init__(convert(value), *args, **kwargs)

    def validate(self, value=None):
        super(type(self), self).validate(convert(value))

    def serialize_value(self, value, settings=None) -> bytes:
        return super(type(self), self).serialize_value(convert(value), settings)

    typ.__init__ = init
    typ.validate = validate
    typ.serialize_value = serialize_value
    return typ


char = _char_type()

u8 = _u8_type('u8', '=B')
i8 = _scalar_type('i8', 1, '=b', RangeValidator(-128, 127))
u16 = _scalar_type('u16', 2, '=H', RangeValidator(0, 65535))
i16 = _scalar_type('i16', 2, '=h', RangeValidator(-32768, 32767))
u32 = _scalar_type('u32', 4, '=I', RangeValidator(0, 4294967295))
i32 = _scalar_type('i32', 4, '=i', RangeValidator(-2147483648, 2147483647))
u64 = _scalar_type('u64', 8, '=Q', RangeValidator(0, 18446744073709551615))
i64 = _scalar_type('i64', 8, '=q', RangeValidator(-9223372036854775808, 9223372036854775807))
f32 = _scalar_type('f32', 4, '=f', FloatValidator(32))
f64 = _scalar_type('f64', 8, '=d', FloatValidator(64))

u8_be = _u8_type('u8_be', '>B')
i8_be = _scalar_type('i8_be', 1, '>b', RangeValidator(-128, 127))
u16_be = _scalar_type('u16_be', 2, '>H', RangeValidator(0, 65535))
i16_be = _scalar_type('i16_be', 2, '>h', RangeValidator(-32768, 32767))
u32_be = _scalar_type('u32_be', 4, '>I', RangeValidator(0, 4294967295))
i32_be = _scalar_type('i32_be', 4, '>i', RangeValidator(-2147483648, 2147483647))
u64_be = _scalar_type('u64_be', 8, '>Q', RangeValidator(0, 18446744073709551615))
i64_be = _scalar_type('i64_be', 8, '>q', RangeValidator(-9223372036854775808, 9223372036854775807))
f32_be = _scalar_type('f32_be', 4, '>f', FloatValidator(32))
f64_be = _scalar_type('f64_be', 8, '>d', FloatValidator(64))

u8_le = _u8_type('u8_le', '<B')
i8_le = _scalar_type('i8_le', 1, '<b', RangeValidator(-128, 127))
u16_le = _scalar_type('u16_le', 2, '<H', RangeValidator(0, 65535))
i16_le = _scalar_type('i16_le', 2, '<h', RangeValidator(-32768, 32767))
u32_le = _scalar_type('u32_le', 4, '<I', RangeValidator(0, 4294967295))
i32_le = _scalar_type('i32_le', 4, '<i', RangeValidator(-2147483648, 2147483647))
u64_le = _scalar_type('u64_le', 8, '<Q', RangeValidator(0, 18446744073709551615))
i64_le = _scalar_type('i64_le', 8, '<q', RangeValidator(-9223372036854775808, 9223372036854775807))
f32_le = _scalar_type('f32_le', 4, '<f', FloatValidator(32))
f64_le = _scalar_type('f64_le', 8, '<d', FloatValidator(64))
