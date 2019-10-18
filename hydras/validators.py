import abc
import struct


class Validator(object):
    @abc.abstractmethod
    def __call__(self, value):
        pass


class TrueValidator(Validator):
    def __call__(self, value):
        pass


class FalseValidator(Validator):
    def __call__(self, value):
        raise ValueError('FalseValidator')


class PredicateValidator(Validator):
    def __init__(self, pred):
        self.pred = pred

    def __call__(self, value):
        if not self.pred(value):
            raise ValueError(f'Invalid value {value}')


class RangeValidator(Validator):
    def __init__(self, min_val, max_val, inclusive=True):
        self.min = min_val
        self.max = max_val + int(bool(inclusive))

    def __call__(self, value):
        if not self.min <= value < self.max:
            raise ValueError(f'Value `{value}` is out of range [{self.min}, {self.max})')


class ExactValueValidator(Validator):
    def __init__(self, expected_value):
        self.expected_value = expected_value

    def __call__(self, value):
        if value != self.expected_value:
            raise ValueError(f'Expected `{self.expected_value}`, got `{value}`')


class FloatValidator(Validator):
    def __init__(self, bit_size):
        assert bit_size in (32, 64)
        self.fmt = '=f' if bit_size == 32 else '=d'

    def __call__(self, value):
        try:
            struct.pack(self.fmt, value)
        except struct.error as e:
            raise ValueError(e.message)


class BitSizeValidator(RangeValidator):
    def __init__(self, max_bit_size):
        assert max_bit_size > 0, f'Expected a positive value for max bit size, got {max_bit_size}'
        super(BitSizeValidator, self).__init__(0, 1 << max_bit_size)


class SetValidator(Validator):
    def __init__(self, items):
        self.items = set(items)

    def __call__(self, value):
        if value not in self.items:
            raise ValueError(f'{value} is not part of the set {self.items}')
