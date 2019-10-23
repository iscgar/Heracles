# Serializer
from .base import *

# Type formatters
from .scalars import *
from .vectors import *
from .struct import *
from .enum import *
# from .bitfield import *
# from .union import *

# Validators
from .validators import *

# Info
__package__ = __name__

__title__ = 'heracles'
__version__ = '0.0.1'

__summary__ = ('heracles is a package which provides simple structured binary'
               ' serialization and deserialization to Python developers for'
               ' easy interop with C.')
__uri__ = 'https://github.com/iscgar/heracles'

__author__ = 'Isaac Garzón'

__license__ = 'MIT'
__copyright__ = f'Copyright 2019 {__author__}'
