import enum
import collections
from typing import Any, ByteString, Callable, Dict, KeysView, Optional, Type, Union as TypeUnion

from ._utils import value_or_default, get_type_name, get_as_type


__all__ = ['Endianness', 'Serializer']


class Endianness(enum.Enum):
    native = '='
    big = '>'
    little = '<'


class MetaDict(collections.OrderedDict):
    def __init__(self, name, onset=None):
        self.name = name
        self.members = collections.OrderedDict()
        self.onset = onset or (lambda m, k, v: v)
        super().__init__()

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self.members:
            raise KeyError(f'`{key}` overrides an existing member')

        result = self.onset(self, key, value)

        if result is not None:
            # Don't add the member to class dict if it's a hidden serializer
            if issubclass(get_as_type(result), Serializer) and result._heracles_hidden_():
                key = f'__heracles_hidden_{self.name}{len(self.members)}_{key}__'
                self.members[key] = result
                return

            self.members[key] = result

        super().__setitem__(key, value)


class SerializerMetadata(object):
    _METAATTR_SIZE = 'size'

    def __init__(self, size: int, **kwargs):
        self.vals = {self._METAATTR_SIZE: size, **kwargs}

    def __getattribute__(self, attr: str) -> Any:
        try:
            return super().__getattribute__(attr)
        except AttributeError:
            return self.vals[attr]

    def __getitem__(self, key: str) -> Any:
        return self.vals[key]

    def __iter__(self) -> KeysView:
        return iter(self.vals)
    
    def keys(self) -> KeysView:
        return self.vals.keys()
    
    def extended(self, **kwargs) -> 'SerializerMetadata':
        for k in kwargs:
            assert k not in self, f'Cannot override existing key `{k}`'
        return SerializerMetadata(**self.vals, **kwargs)


class SerializerMeta(type):
    METAATTR = '__heracles_metadata'

    @staticmethod
    def create_array(size: TypeUnion[int, slice], underlying: Type['Serializer']):
        from .array import Array
        if isinstance(size, (int, slice)):
            return Array[size, underlying]
        else:
            raise ValueError(f'Expected an int or a slice, got {get_type_name(size)}')

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


class Serializer(metaclass=SerializerMeta):
    # TODO: stack validators?
    def __init__(self, value: Any, *, validator: Optional[Callable[[Any], None]] = None):
        self._heracles_validator = validator
        self._heracles_value = value
        self._heracles_validate_(value)

    @classmethod
    def _heracles_metadata_(cls) -> SerializerMetadata:
        return getattr(cls, SerializerMeta.METAATTR, None)

    @classmethod
    def _heracles_hidden_(cls) -> bool:
        return False

    @classmethod
    def _heracles_vst_(cls) -> bool:
        return False

    @classmethod
    def _heracles_bytesize_(cls, value: Optional[Any] = None) -> int:
        return cls._heracles_metadata_().size

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
        if self._heracles_validator is not None:
            self._heracles_validator(self._get_serializer_value(value))
        return value

    def _heracles_render_(self, value: Optional[Any] = None) -> str:
        value = self._get_serializer_value(value)
        return f'{get_type_name(self)}({self._heracles_validate_(value)})'
    
    def _heracles_compare_(self, other: Any, value: Optional[Any] = None) -> bool:
        return self._get_serializer_value(value) == self._get_serializer_value(other)

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
