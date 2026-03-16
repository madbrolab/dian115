#!/usr/bin/env python3
# encoding: utf-8

from __future__ import annotations

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "AVAILABLE_APPS", "APP_TO_SSOENT", "SSOENT_TO_APP", "CLIENT_METHOD_API_MAP", 
    "CLIENT_API_METHODS_MAP", "CLASS_TO_TYPE", "SUFFIX_TO_TYPE", "TYPE_TO_SUFFIXES", 
    "ID_TO_DIRNODE_CACHE", "WEPAPI_PREFIXES", 
]

from collections import defaultdict
from collections.abc import MutableMapping
from pathlib import Path
from typing import Final

from iter_collect import grouped_mapping


_CACHE_DIR = Path("~/.p115client.cache.d").expanduser()
_CACHE_DIR.mkdir(exist_ok=True)

#: 目前可用的登录设备
AVAILABLE_APPS: Final[dict[str, str]] = {
    "web": "115生活_网页端", 
    "ios": "115生活_苹果端", 
    "115ios": "115_苹果端", 
    "android": "115生活_安卓端", 
    "115android": "115_安卓端", 
    "ipad": "115生活_苹果平板端", 
    "115ipad": "115_苹果平板端", 
    "tv": "115生活_安卓电视端", 
    "apple_tv": "115生活_苹果电视端", 
    "qandroid": "115管理_安卓端", 
    "qios": "115管理_苹果端", 
    "qipad": "115管理_苹果平板端", 
    "os_windows": "115生活_Windows端", 
    "os_mac": "115生活_macOS端", 
    "os_linux": "115生活_Linux端", 
    "wechatmini": "115生活_微信小程序端", 
    "alipaymini": "115生活_支付宝小程序", 
    "harmony": "115_鸿蒙端", 
}

#: 目前已知的登录设备和对应的 ssoent
APP_TO_SSOENT: Final[dict[str, str]] = {
    "web": "A1", 
    "desktop": "A1", 
    "ios": "D1", 
    "bios": "D2", 
    "115ios": "D3", 
    "android": "F1", 
    "bandroid": "F2", 
    "115android": "F3", 
    "ipad": "H1", 
    "bipad": "H2", 
    "115ipad": "H3", 
    "tv": "I1", 
    "apple_tv": "I2", 
    "qandroid": "M1", 
    "qios": "N1", 
    "qipad": "O1", 
    "os_windows": "P1", 
    "os_mac": "P2", 
    "os_linux": "P3", 
    "windows": "P1", 
    "mac": "P2", 
    "linux": "P3", 
    "wechatmini": "R1", 
    "alipaymini": "R2", 
    "harmony": "S1", 
}

#: 目前已知的 ssoent 和对应的登录设备，一部分因为不知道具体的设备名，所以使用目前可用的设备名，作为临时代替
SSOENT_TO_APP: Final[dict[str, str]] = {v: k for k, v in reversed(APP_TO_SSOENT.items())}

#: 所有已封装的方法名和对应的 115 接口
CLIENT_METHOD_API_MAP: Final[dict[str, str]] = {}

#: 所有已封装的 115 接口和对应的方法名
CLIENT_API_METHODS_MAP: Final[dict[str, list[str]]] = {}

#: 文件的 class 属性对应的所属类型的整数代码
CLASS_TO_TYPE: Final[dict[str, int]] = {
    "JG_DOC": 1, 
    "DOC": 1, 
    "JG_PIC": 2, 
    "PIC": 2, 
    "JG_MUS": 3, 
    "MUS": 3, 
    "JG_AVI": 4, 
    "AVI": 4, 
    "JG_RAR": 5, 
    "RAR": 5, 
    "RAR_EXTRACT": 5, 
    "JG_EXE": 6, 
    "EXE": 6, 
    "JG_BOOK": 7, 
    "BOOK": 7
}

#: 文件后缀对应的所属类型的整数代码（尚需补充）
SUFFIX_TO_TYPE: Final[dict[str, int]] = {
    ".ass": 1, # subtitle
    ".chm": 1, 
    ".csv": 1, 
    ".doc": 1, 
    ".docm": 1, 
    ".docx": 1, 
    ".dotm": 1, 
    ".dot": 1, 
    ".dps": 1, 
    ".dwg": 1, 
    ".et": 1, 
    ".htm": 1, 
    ".html": 1, 
    ".idx": 1, 
    ".jar": 1, 
    ".key": 1, 
    ".log": 1, 
    ".lrc": 1, # subtitle
    ".md": 1, 
    ".mdb": 1, 
    ".mdf": 1, 
    ".numbers": 1, 
    ".ods": 1, 
    ".odt": 1, 
    ".pages": 1, 
    ".pdf": 1, 
    ".pot": 1, 
    ".pps": 1, 
    ".ppt": 1, 
    ".pptm": 1, 
    ".pptx": 1, 
    ".rtf": 1, 
    ".srt": 1, # subtitle
    ".ssa": 1, # subtitle
    ".sub": 1, # subtitle
    ".torrent": 1, 
    ".txt": 1, 
    ".wps": 1, 
    ".wri": 1, 
    ".xlam": 1, 
    ".xls": 1, 
    ".xlsb": 1, 
    ".xlsm": 1, 
    ".xlsx": 1, 
    ".xltm": 1, 
    ".xltx": 1, 
    ".vtt": 1, # subtitle
    ".avif": 2, 
    ".bmp": 2, 
    ".dng": 2, 
    ".exif": 2, 
    ".gif": 2, 
    ".heic": 2, 
    ".heif": 2, 
    ".ico": 2, 
    ".jfif": 2, 
    ".jpeg": 2, 
    ".jpg": 2, 
    ".png": 2, 
    ".psd": 2, 
    ".raw": 2, 
    ".svg": 2, 
    ".tif": 2, 
    ".tiff": 2, 
    ".webp": 2, 
    ".aac": 3, 
    ".ac3": 3, 
    ".aiff": 3, 
    ".alac": 3, 
    ".amr": 3, 
    ".ape": 3, 
    ".au": 3, 
    ".dsf": 3, 
    ".dts": 3, 
    ".f4a": 3, 
    ".flac": 3, 
    ".m4a": 3, 
    ".mid": 3, 
    ".midi": 3, 
    ".mp3": 3, 
    ".ogg": 3, 
    ".opus": 3, 
    ".ra": 3, 
    ".wav": 3, 
    ".wma": 3, 
    ".wv": 3, 
    ".3g2": 4, 
    ".3gp": 4, 
    ".3gp2": 4, 
    ".3gpp": 4, 
    ".asf": 4, 
    ".avi": 4, 
    ".dat": 4, 
    ".divx": 4, 
    ".f4v": 4, 
    ".flv": 4, 
    ".iso": 4, 
    ".m2ts": 4, 
    ".m4v": 4, 
    ".mkv": 4, 
    ".mov": 4, 
    ".mp4": 4, 
    ".mpe": 4, 
    ".mpeg": 4, 
    ".mpeg4": 4, 
    ".mpg": 4, 
    ".mts": 4, 
    ".ogv": 4, 
    ".ram": 4, 
    ".rm": 4, 
    ".rmvb": 4, 
    ".swf": 4, 
    ".ts": 4, 
    ".vob": 4, 
    ".webm": 4, 
    ".wmv": 4, 
    ".7z": 5, 
    ".bz2": 5, 
    ".cab": 5, 
    ".dmg": 5, 
    ".gz": 5, 
    #".iso": 5, 
    ".msi": 5, 
    ".part": 5, 
    ".rar": 5, 
    ".tar": 5, 
    ".xz": 5, 
    ".z": 5, 
    ".zip": 5, 
    ".apk": 6, 
    ".app": 6, 
    ".bat": 6, 
    ".deb": 6, 
    #".dmg": 6, 
    ".exe": 6, 
    ".ipa": 6, 
    #".msi": 6, 
    ".pkg": 6, 
    ".rpm": 6, 
    ".azw": 7, 
    ".azw3": 7, 
    ".epub": 7, 
    ".fb2": 7, 
    ".lit": 7, 
    ".lrf": 7, 
    ".mobi": 7, 
    ".prc": 7, 
}

#: 文件类型的整数代码对应的扩展名元组
TYPE_TO_SUFFIXES: Final[dict[int, tuple[str, ...]]] = {
    k: tuple(v) for k, v in grouped_mapping(
        (v, k) for k, v in SUFFIX_TO_TYPE.items()).items()}

#: 用于缓存每个用户或者分享，的每个目录 id 到所对应的 (name, parent_id) 的元组的字典的字典
ID_TO_DIRNODE_CACHE: Final[dict[int | str, MutableMapping[int, tuple[str, int]]]] = defaultdict(dict)

#: 一些 webapi.115.com 的接口允许的前缀（而 proapi.115.com 却可以是任何前缀）
WEPAPI_PREFIXES = (
    "/behavior", "/category", "/files", "/history", "/label", "/movies", 
    "/offine", "/photo", "/rb", "/share", "/user", "/usershare", 
)
