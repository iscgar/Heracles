"""
Contains the core classes of the framework.

:file: base.py
:date: 27/08/2015
:authors:
    - Gilad Naaman <gilad@naaman.io>
"""

import abc
import collections
from typing import Dict, Any

from .utils import *


class HydraSettings(object):
    """ Contains global default settings. """
    # Determines whether the object will be validated on serialize.
    validate_on_serialize = False

    # Determines whether the size of the bitfield's fields will be enforced.
    enforce_bitfield_size = True

    # Determines whether parsed enum literals have to be part of the enum.
    strong_enum_literals = True

    # When True, renders enum values as integers instead of strings.
    render_enums_as_integers = False

    # When True and `render_enums_as_integers == False`, renders enum literals as "EnumName.LiteralName"
    full_enum_names = True

    @classmethod
    def resolve(cls, *args):
        """ Resolve settings dictionaries."""
        global_settings = cls.snapshot()

        for overrides in args:
            if overrides is not None and isinstance(overrides, dict):
                global_settings.update(overrides)

        return global_settings

    @classmethod
    def snapshot(cls):
        """ Retrieve a snapshot of the settings at the moment of the call. """
        return {name: value for name, value in vars(cls).items()
                if (not name.startswith('_')) and (type(value) is not classmethod)}

    @classmethod
    def update(cls, new_settings):
        """
        Update the global settings according to the given dictionary.
        Preferences not found in the new dictionary will retain their values.
        Unrecognized keys will be ignored.

        :param new_settings:    A dictionary containing overrides of the settings.
        :return:                A snapshot of the new settings.
        """
        for var, value in new_settings.items():
            if var in vars(cls):
                setattr(cls, var, value)

        return cls.snapshot()


class SerializerMetadata(object):
    _METAATTR_NAME = 'name'
    _METAATTR_SIZE = 'size'

    def __init__(self, name, size, **kwargs):
        self.vals = {
            self._METAATTR_NAME: name,
            self._METAATTR_SIZE: size,
            **kwargs
        }

    def __getitem__(self, name):
        return getattr(self, 'vals')[name]

    def __getattr__(self, name):
        return self[name]


class SerializerMeta(type):
    METAATTR = '_metadata'

    def __call__(cls, *args, settings=None, **kwargs):
        try:
            return super(SerializerMeta, cls).__call__(*args, settings=settings, **kwargs)
        except Exception:
            # TODO: handle settings as args[1]
            if not kwargs and len(args) == 1 and isinstance(args[0], bytes):
                return cls().deserialize(args[0], settings)
            raise

    def __getitem__(cls, size):
        """
        This hack enables the familiar array syntax: `type[count]`.
        For example, a 3-item array of type uint8_t might look like `uint8_t[3]`.
        """
        # Importing locally in order to avoid weird import-cycle issues
        from .vectors import Array, VariableArray
        if isinstance(size, int):
            return Array(size, cls)
        elif isinstance(size, slice):
            assert size.step is None, 'Cannot supply step as array size'
            return VariableArray(size.start, size.stop, cls)
        else:
            raise ValueError(f'Expected an int or a slice, got {get_type_name(size)}')

    def __len__(cls) -> int:
        if not cls.constant_size():
            return 0

        return cls.metadata().size


class Serializer(metaclass=SerializerMeta):
    def __init__(self, value, validator=None, settings=None):
        self.validator = get_as_value(validator)
        self.settings = settings or {}
        self._value = value
        self.validate(value)

    def __bytes__(self) -> bytes:
        return self.serialize()

    @property
    def value(self):
        return self._value  

    @classmethod
    def metadata(cls) -> SerializerMetadata:
        return getattr(cls, SerializerMeta.METAATTR, None)

    @classmethod
    def hidden(cls) -> bool:
        return False

    def get_serializer_value(self, value=None):
        value = value_or_default(value, self)
        if issubclass(type(value), Serializer):
            value = value.value
        return value

    def serialize(self, settings=None) -> bytes:
        return self.serialize_value(self.value, settings)

    @abc.abstractmethod
    def serialize_value(self, value, settings={}) -> bytes:
        raise NotImplemntedError()

    @abc.abstractmethod
    def deserialize(self, raw_data, settings={}):
        raise NotImplemntedError()

    def validate(self, value=None):
        if hasattr(self.validator, '__call__'):
            self.validator(self.get_serializer_value(value))

    @classmethod
    def constant_size(cls) -> bool:
        return True

    def __eq__(self, other) -> bool:
        return self.value == (
            other.value if issubclass(type(other), Serializer) else other)

    def __ne__(self, other) -> bool:
        return not self.value == other

    def __repr__(self) -> str:
        return f'{get_type_name(self)}({self.value})'

    def __len__(self) -> int:
        return len(type(self))

    def __getitem__(self, size):
        """
        This hack enables the familiar array syntax: `type()[count]`.
        For example, a 3-item array of type uint16_t might look like `uint16_t(endian=BigEndian)[3]`.
        """
        # Importing locally in order to avoid weird import-cycle issues
        from .vectors import Array, VariableArray
        if isinstance(size, int):
            return Array(size, self)
        elif isinstance(size, slice):
            assert size.step is None, 'Cannot supply step as array size'
            return VariableArray(size.start, size.stop, self)
        else:
            raise ValueError(f'Expected an int or a slice, got {get_type_name(size)}')
