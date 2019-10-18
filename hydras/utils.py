import collections
import inspect


def get_as_type(t):
    return t if inspect.isclass(t) else type(t)


def get_as_value(v):
    return v() if inspect.isclass(v) else v


def get_type_name(t):
    return t.__class__.__name__


def indexof(callable, it):
    for i, v in enumerate(it):
        if callable(v):
            return i
    raise ValueError


def mask(length, offset=0):
    """
    Generate a bitmask with the given parameter.

    :param length:  The bit length of the mask.
    :param offset:  The offset of the mask from the LSB bit. [default: 0]
    :return:        An integer representing the bit mask.
    """
    return ((1 << length) - 1) << offset


def padto(data, size, pad_val=b'\x00', leftpad=False):
    assert isinstance(pad_val, bytes) and len(pad_val) == 1, 'Padding value must be 1 byte'
    if len(data) < size:
        padding = pad_val * (size - len(data))

        if not leftpad:
            data += padding
        else:
            data = padding + data
    return data


def value_or_default(value, default):
    return value if value is not None else default


def first(it):
    return next(iter(it))


def last(it):
    return next(reversed(it))


class MetaDict(collections.OrderedDict):
    def __init__(self, onset):
        super(MetaDict, self).__init__()
        self.members = []
        self.onset = onset

    def __setitem__(self, name, value):
        fmt = self.onset(self.members, name, value)

        if fmt is not None:
            if name in self:
                raise RuntimeError(f'field {name} overrides existing member')

            self.members.append((None if fmt.hidden() else name, fmt))

            if fmt.hidden():
                return

        super(MetaDict, self).__setitem__(name, value)
