import abc
import struct
from typing import Any, Callable, Iterable, Union as TypeUnion

from ._utils import get_type_name


class Validator(abc.ABC):
    @abc.abstractmethod
    def __call__(self, value: Any) -> None:
        pass


class TrueValidator(Validator):
    def __call__(self, value: Any) -> None:
        pass


class FalseValidator(Validator):
    def __call__(self, value: Any) -> None:
        raise ValueError('FalseValidator')


class PredicateValidator(Validator):
    def __init__(self, pred: Callable[[Any], bool]):
        if not hasattr(pred, '__call__'):
            raise TypeError(f'{get_type_name(pred)} is not callable')
        self.pred = pred

    def __call__(self, value: Any) -> None:
        if not self.pred(value):
            raise ValueError(f'Calling {get_type_name(self.pred)}({value}) returned False')


class ExactValueValidator(Validator):
    def __init__(self, expected_value: Any):
        self.expected_value = expected_value

    def __call__(self, value: Any) -> None:
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

    def __call__(self, value: TypeUnion[int, float]) -> None:
        try:
            struct.pack(self.fmt, value)
        except struct.error as e:
            raise ValueError(e.message)


class AsciiCharValidator(Validator):
    def __call__(self, value):
        if isinstance(value, str):
            value = value.encode('ascii')
        if not isinstance(value, bytes) or len(value) != 1:
            raise ValueError(f'Expected ASCII str of length 1, got {value}')


class BitSizeValidator(IntRangeValidator):
    def __init__(self, max_bit_size: int):
        if max_bit_size <= 0:
            raise ValueError(f'Expected a positive value for max bit size, got {max_bit_size}')
        super().__init__(0, 1 << max_bit_size)


class SetValidator(Validator):
    def __init__(self, items: Iterable[Any]):
        self.items = set(items)

    def __call__(self, value: Any) -> None:
        if value not in self.items:
            raise ValueError(f'{value} is not part of the set {self.items}')
