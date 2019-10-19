import abc
import struct
import typing


class Validator(object):
    @abc.abstractmethod
    def __call__(self, value: typing.Any) -> None:
        pass


class TrueValidator(Validator):
    def __call__(self, value: typing.Any) -> None:
        pass


class FalseValidator(Validator):
    def __call__(self, value: typing.Any) -> None:
        raise ValueError('FalseValidator')


class PredicateValidator(Validator):
    def __init__(self, pred: typing.Callable[[typing.Any], bool]):
        self.pred = pred

    def __call__(self, value: typing.Any) -> None:
        if not self.pred(value):
            raise ValueError(f'Invalid value {value}')


class ExactValueValidator(Validator):
    def __init__(self, expected_value: typing.Any):
        self.expected_value = expected_value

    def __call__(self, value: typing.Any) -> None:
        if value != self.expected_value:
            raise ValueError(f'Expected `{self.expected_value}`, got `{value}`')


class IntRangeValidator(Validator):
    def __init__(self, min_val, max_val, inclusive: bool=True):
        self.min = min_val
        self.max = max_val + int(bool(inclusive))

    def __call__(self, value: int) -> None:
        if not isinstance(value, int):
            raise ValueError(f'Expected int, got {type(value)}')

        if not self.min <= value < self.max:
            raise ValueError(f'Value `{value}` is out of range [{self.min}, {self.max})')


class FloatValidator(Validator):
    def __init__(self, bit_size: int):
        if bit_size not in (32, 64):
            raise ValueError(f'Unsupported float size {bit_size}')
        self.fmt = '=f' if bit_size == 32 else '=d'

    def __call__(self, value: typing.Union[int, float]) -> None:
        try:
            struct.pack(self.fmt, value)
        except struct.error as e:
            raise ValueError(e.message)


class BitSizeValidator(IntRangeValidator):
    def __init__(self, max_bit_size: int):
        if max_bit_size <= 0:
            raise ValueError(f'Expected a positive value for max bit size, got {max_bit_size}')
        super().__init__(0, 1 << max_bit_size)


class SetValidator(Validator):
    def __init__(self, items: typing.Iterable[typing.Any]):
        self.items = set(items)

    def __call__(self, value: typing.Any) -> None:
        if value not in self.items:
            raise ValueError(f'{value} is not part of the set {self.items}')
