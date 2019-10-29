import enum
import collections
from typing import Any, ByteString, Callable, Dict, Iterator, KeysView, Optional, Type, Union as TypeUnion

from ._utils import value_or_default, type_name, is_type, as_type, as_iter, metaclassmethod


__all__ = ['Endianness', 'Serializer', 'byte_size']


class HiddenSentinal(object):
    pass


class Endianness(enum.Enum):
    native = '='
    big = '>'
    little = '<'


class MetaDict(collections.OrderedDict):
    ignore = object()

    def __init__(self, name, onset=None):
        self.name = name
        self.members = collections.OrderedDict()
        self.onset = onset or (lambda m, k, v: v)
        super().__init__()

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self.members:
            raise KeyError(f'`{key}` overrides an existing member of {self.name}')
        result = self.onset(self, key, value)
        if result is not self.ignore:
            super().__setitem__(key, value)


class SerializerMetadata(object):
    __slots__ = ('byte_size',)

    def __init__(self, byte_size: int):
        self.byte_size = byte_size

    def __setattr__(self, key: str, value: Any):
        if hasattr(self, key):
            raise AttributeError(f'Cannot reassign {key}')
        super().__setattr__(key, value)
    
    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError as e:
            raise KeyError(e.message)

    def __iter__(self) -> Iterator:
        return (k for k in dir(self) if not k.startswith('_'))


class SerializerMeta(type):
    METAATTR = '__heracles_metadata'
    RESERVED_ATTRS = ('__metadata__', '__bytesize__', '__ishidden__', '__isvst__', '__iswrapper__', METAATTR)

    @staticmethod
    def create_array(size: TypeUnion[int, slice], underlying: Type['Serializer']):
        from .array import Array
        if not isinstance(size, (int, slice)):
            raise ValueError(f'Expected an int or a slice, got {type_name(size)}')
        return Array[size, underlying]
    
    @property
    def __metadata__(cls) -> SerializerMetadata:
        return getattr(cls, SerializerMeta.METAATTR)

    @metaclassmethod
    def __bytesize__(cls) -> int:
        return cls.__metadata__.byte_size

    @property
    def __isvst__(cls) -> bool:
        return False

    @property
    def __ishidden__(cls) -> bool:
        return False

    @property
    def __iswrapper__(cls) -> bool:
        return False

    def __call__(cls, *args, settings: Dict[str, Any] = None, **kwargs) -> 'Serializer':
        try:
            if settings is not None:
                kwargs['settings'] = settings
            return super().__call__(*args, **kwargs)
        except Exception as e:
            if not kwargs and len(args) == 1 and isinstance(args[0], bytes):
                # TODO: Don't create an unnecessary instance
                return cls().deserialize(args[0], settings=settings)
            raise

    def __getitem__(cls, size: TypeUnion[int, slice]):
        return cls.create_array(size, cls)

    @staticmethod
    def _validate_setattr(obj, name: str):
        if name.startswith('_heracles') and hasattr(obj, name):
            raise AttributeError(f'{type_name(obj)}: Cannot reassign heracles attribute `{name}`')
        elif name in Serializer.RESERVED_ATTRS:
            raise AttributeError(
                f'{type_name(obj)}: `{name}` is reserved for the heracles implementation')

    def __setattr__(cls, name: str, value: Any):
        cls._validate_setattr(cls, name)
        return super().__setattr__(name, value)


class Serializer(metaclass=SerializerMeta):
    def __new__(cls, *args, **kwargs):
        # Make sure we have metadata
        try:
            assert isinstance(cls.__metadata__, SerializerMetadata)
        except (AttributeError, AssertionError):
            raise TypeError('Cannot instantiate an abstarct Serializer class')
        return super().__new__(cls)
        
    def __init__(self, value: Any, *, validator: Optional[Callable[[Any], None]] = None):
        self._heracles_validator = tuple(as_iter(validator))
        self._heracles_value = value
        self._heracles_validate_(value)

    @property
    def __metadata__(self) -> SerializerMetadata:
        return type(self).__metadata__

    @property
    def __isvst__(self) -> bool:
        return type(self).__isvst__

    @property
    def __ishidden__(self) -> bool:
        return type(self).__ishidden__

    @property
    def __iswrapper__(self) -> bool:
        return type(self).__iswrapper__

    def __bytesize__(self, value: Optional[Any] = None) -> int:
        return type(self).__bytesize__()

    def _get_serializer_value(self, value: Optional[Any] = None):
        value = value_or_default(value, self)
        if issubclass(type(value), Serializer):
            value = value.value
        return value

    def serialize(self, settings: Optional[Dict[str, Any]] = None) -> bytes:
        return self.serialize_value(self.value, settings)

    def serialize_value(self, value: Any, settings: Optional[Dict[str, Any]] = {}) -> bytes:
        raise NotImplementedError()

    def deserialize(self, raw_data: ByteString, settings: Optional[Dict[str, Any]] = {}):
        raise NotImplementedError()

    def _heracles_validate_(self, value: Optional[Any] = None) -> Any:
        value = self._get_serializer_value(value)
        for validator in self._heracles_validator:
            validator(value)
        return value

    def _heracles_render_(self, value: Optional[Any] = None) -> str:
        return f'{type_name(self)}({self._heracles_validate_(value)})'

    def _heracles_compare_(self, other: Any, value: Optional[Any] = None) -> bool:
        return self._heracles_validate_(value) == self._heracles_validate_(other)

    @property
    def value(self) -> Any:
        return self._heracles_value

    def __bytes__(self) -> bytes:
        return self.serialize()

    def __eq__(self, other: Any) -> bool:
        return self._heracles_compare_(other)

    def __ne__(self, other: Any) -> bool:
        return not self._heracles_compare_(other)

    def __repr__(self) -> str:
        return self._heracles_render_()

    def __getitem__(self, size: TypeUnion[int, slice]):
        return type(self).create_array(size, self)
    
    def __setattr__(self, name: str, value: Any):
        type(self)._validate_setattr(self, name)
        return super().__setattr__(name, value)


def isvst(serializer: TypeUnion[Serializer, Type[Serializer]]) -> bool:
    try:
        return serializer.__isvst__
    except AttributeError:
        raise TypeError(f'Expected a Serializer, got {type_name(serializer)}')


def ishidden(serializer: TypeUnion[Serializer, Type[Serializer]]) -> bool:
    try:
        return serializer.__ishidden__
    except AttributeError:
        raise TypeError(f'Expected a Serializer, got {type_name(serializer)}')


def iswrapper(serializer: TypeUnion[Serializer, Type[Serializer]]) -> bool:
    try:
        return serializer.__iswrapper__
    except AttributeError:
        raise TypeError(f'Expected a Serializer, got {type_name(serializer)}')


def byte_size(serializer: TypeUnion[Serializer, Type[Serializer]], value: Optional[Any] = None) -> int:
    try:
        if value is None:
            return serializer.__bytesize__()
        else:
            return serializer.__bytesize__(value)
    except (TypeError, AttributeError):
        raise TypeError(f'Expected a Serializer, got {type_name(serializer)}')
