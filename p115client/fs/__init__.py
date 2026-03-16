#!/usr/bin/env python3
# encoding: utf-8

from .fs_base import *
from .fs import *
from .fs_share import *
from .fs_zip import *

def __getattr__(attr, /):
    if attr == "__all__":
        from . import fs_base, fs, fs_share, fs_zip
        return fs_base.__all__ + fs.__all__ + fs_share.__all__ + fs_zip.__all__
    raise AttributeError(attr)
