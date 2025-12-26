# services/__init__.py
# -*- coding: utf-8 -*-
"""
业务逻辑层
将复杂的业务逻辑从路由中抽离，提高代码复用性
"""

from .json_helper import load_json, save_json
from .ec_service import decode_from_dict

__all__ = [
    'load_json',
    'save_json',
    'decode_from_dict',
]
