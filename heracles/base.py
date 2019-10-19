import collections
import typing

from .utils import value_or_default, get_type_name, get_as_type


__all__ = ['Serializer']


class MetaDict(collections.OrderedDict):
    def __init__(self, name, onset):
        self.name = name
        self.members = collections.OrderedDict()
        self.onset = onset
        super().__init__()
    
    def gen_hidden_name(self, name: str, hint: typing.Optional[int]=None) -> str:
        if hint is None:
            hint = len(self.members)
        return f'__heracles_hidden{hint}_{self.name}_{name}__'

    def __setitem__(self, name: str, value: typing.Any) -> None:
        result = self.onset(self.members, name, value)

        if result is not None:
            if name in self:
                raise RuntimeError(f'`{name}` overrides an existing member')

            if issubclass(get_as_type(result), Serializer) and result.hidden():
                self.members[self.gen_hidden_name(name)] = result
                return

            self.members[name] = result

        super().__setitem__(name, value)


class SerializerMetadata(object):
    _METAATTR_SIZE = 'size'

    def __init__(self, size: int, **kwargs):
        self.vals = {
            self._METAATTR_SIZE: size,
            **kwargs
        }

    def __getitem__(self, name: str) -> typing.Any:
        return getattr(self, 'vals')[name]

    def __getattr__(self, name: str) -> typing.Any:
        return self[name]
    
    def items(self) -> typing.Iterable:
        return self.vals.items()


class SerializerMeta(type):
    METAATTR = '_metadata'

    @staticmethod
    def _create_array(size, underlying):
        from .vectors import Array, VariableArray
        if isinstance(size, int):
            return Array(size, underlying)
        elif isinstance(size, slice):
            assert size.step is None, 'Cannot supply step as array size'
            return VariableArray(size.start, size.stop, underlying)
        else:
            raise ValueError(f'Expected an int or a slice, got {get_type_name(size)}')

    def __call__(cls, *args, settings: typing.Dict[str, typing.Any]=None, **kwargs) -> 'Serializer':
        try:
            if settings is not None:
                kwargs['settings'] = settings
            return super().__call__(*args, **kwargs)
        except Exception as e:
            # TODO: handle settings as args[1]
            if not kwargs and len(args) == 1 and isinstance(args[0], bytes):
                # TODO: Don't create an unnecessary instance
                return cls().deserialize(args[0], settings)
            raise

    def __getitem__(cls, size: typing.Union[int, slice]):
        return cls._create_array(size, cls)

    def __len__(cls) -> int:
        if not cls.constant_size():
            return 0

        return cls.metadata().size


class Serializer(metaclass=SerializerMeta):
    def __init__(self, value: typing.Any, *, validator: typing.Optional[typing.Callable[[typing.Any], None]]=None):
        self.validator = validator
        self._value = value
        self.validate(value)

    @classmethod
    def metadata(cls) -> SerializerMetadata:
        return getattr(cls, SerializerMeta.METAATTR, None)

    @classmethod
    def hidden(cls) -> bool:
        return False

    @classmethod
    def constant_size(cls) -> bool:
        return True

    def get_serializer_value(self, value: typing.Optional[typing.Any]=None):
        value = value_or_default(value, self)
        if issubclass(type(value), Serializer):
            value = value.value
        return value

    def serialize(self, settings: typing.Optional[typing.Dict[str, typing.Any]]=None) -> bytes:
        return self.serialize_value(self.value, settings)

    def serialize_value(self, value: typing.Any, settings: typing.Optional[typing.Dict[str, typing.Any]]={}) -> bytes:
        raise NotImplementedError()

    def deserialize(self, raw_data: typing.ByteString, settings: typing.Optional[typing.Dict[str, typing.Any]]={}):
        raise NotImplementedError()

    def validate(self, value: typing.Optional[typing.Any]=None) -> typing.Any:
        if hasattr(self.validator, '__call__'):
            self.validator(self.get_serializer_value(value))
        return value

    def render(self, value: typing.Optional[typing.Any]=None) -> str:
        value = self.get_serializer_value(value)
        return f'{get_type_name(self)}({self.validate(value)})'
    
    def compare(self, other: typing.Any, value: typing.Optional[typing.Any]=None) -> bool:
        return self.get_serializer_value(value) == self.get_serializer_value(other)

    @property
    def value(self) -> typing.Any:
        return self._value

    def __bytes__(self) -> bytes:
        return self.serialize()

    def __eq__(self, other: typing.Any) -> bool:
        return self.compare(other)

    def __ne__(self, other: typing.Any) -> bool:
        return not self.compare(other)

    def __repr__(self) -> str:
        return self.render()

    def __len__(self) -> int:
        return len(type(self))

    def __getitem__(self, size: typing.Union[int, slice]):
        return type(self)._create_array(size, self)
