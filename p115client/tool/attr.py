#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = [
    "normalize_attr", "normalize_attr_simple", "normalize_attr_web", 
    "normalize_attr_app", "normalize_attr_app2", 
    "type_of_attr", "get_attr", "get_info", "iter_list", 
    "get_ancestors", "get_path", "get_id", "get_id_to_path", 
    "get_id_to_sha1", "get_id_to_name", "share_get_id", 
    "share_get_id_to_path", "share_get_id_to_name", "get_file_count", 
]
__doc__ = "这个模块提供了一些和文件或目录信息有关的函数"

from collections.abc import (
    AsyncIterator, Callable, Coroutine, Iterable, Iterator, 
    Mapping, MutableMapping, Sequence, 
)
from functools import partial
from itertools import cycle, dropwhile
from operator import attrgetter
from os import PathLike
from types import EllipsisType
from typing import cast, overload, Any, Final, Literal

from dictattr import AttrDict
from dicttools import get_first
from errno2 import errno
from integer_tool import try_parse_int
from iterutils import run_gen_step, run_gen_step_iter, with_iter_next, Yield
from p115pickcode import to_id
from posixpatht import path_is_dir_form, splitext, splits

from ..client import check_response, P115Client, P115OpenClient
from ..const import CLASS_TO_TYPE, SUFFIX_TO_TYPE, ID_TO_DIRNODE_CACHE
from ..exception import throw
from ..type import P115ID
from ..util import (
    posix_escape_name, share_extract_payload, unescape_115_charref, 
    is_valid_id, is_valid_sha1, is_valid_name, is_valid_pickcode, 
)

@overload
def normalize_attr_web(
    info: Mapping[str, Any], 
    /, 
    simple: bool = False, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: None = None, 
) -> dict[str, Any]:
    ...
@overload
def normalize_attr_web[D: dict[str, Any]](
    info: Mapping[str, Any], 
    /, 
    simple: bool = False, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: type[D], 
) -> D:
    ...
def normalize_attr_web[D: dict[str, Any]](
    info: Mapping[str, Any], 
    /, 
    simple: bool = False, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: None | type[D] = None, 
) -> dict[str, Any] | D:
    """翻译 ``P115Client.fs_files()``、``P115Client.fs_search()``、``P115Client.share_snap()`` 等方法响应的文件信息数据，使之便于阅读

    :param info: 原始数据
    :param simple: 只提取少量必要字段 "is_dir", "id", "parent_id", "name", "sha1", "size", "pickcode", "is_collect", "ctime", "mtime", "type"
    :param keep_raw: 是否保留原始数据，如果为 True，则保存到 "raw" 字段
    :param default: 一些预设值，可被覆盖
    :param dict_cls: 字典类型

    :return: 翻译后的 dict 类型数据
    """
    if dict_cls is None:
        dict_cls = cast(type[D], dict)
    attr: dict[str, Any] = dict_cls()
    if default:
        attr.update(default)
    is_dir = attr["is_dir"] = "fid" not in info
    if is_dir:
        attr["id"] = int(info["cid"])        # category_id
        attr["parent_id"] = int(info["pid"]) # parent_id
    else:
        attr["id"] = int(info["fid"])        # file_id
        attr["parent_id"] = int(info["cid"]) # category_id
    attr["name"] = info.get("n") or info["file_name"]
    attr["sha1"] = info.get("sha") or ""
    attr["size"] = int(info.get("s") or 0)
    if "pc" in info:
        attr["pickcode"] = info["pc"]
    if simple:
        if "c" in info:
            attr["is_collect"] = int(info["c"])
        if "tp" in info:
            attr["ctime"] = int(info["tp"])
        if "te" in info:
            attr["mtime"] = int(info["te"])
    else:
        if "pickcode" in attr:
            attr["pick_code"] = attr["pickcode"]
        attr["ico"] = info.get("ico", "folder" if is_dir else "")
        if "te" in info:
            attr["mtime"] = attr["user_utime"] = int(info["te"])
        if "tp" in info:
            attr["ctime"] = attr["user_ptime"] = int(info["tp"])
        if "to" in info:
            attr["atime"] = attr["user_otime"] = int(info["to"])
        if "tu" in info:
            attr["utime"] = int(info["tu"])
        if t := info.get("t"):
            attr["time"] = try_parse_int(t)
        if "fdes" in info:
            val = info["fdes"]
            if isinstance(val, str):
                attr["desc"] = val
            attr["has_desc"] = 1 if val else 0
        for key, name in (
            ("aid", "area_id"), 
            ("all_skip_login", "all_skip_login"), 
            ("audio_play_long", "audio_play_long"), 
            ("c", "is_collect"), 
            ("cc", "cover"), 
            ("cc", "category_cover"), 
            ("class", "class"), 
            ("current_time", "current_time"), 
            ("d", "has_desc"), 
            ("dp", "dir_path"), 
            ("e", "pick_expire"), 
            ("fl", "labels"), 
            ("hdf", "is_private"), 
            ("is_skip_login", "is_skip_login"), 
            ("is_top", "is_top"), 
            ("ispl", "show_play_long"), 
            ("issct", "is_shortcut"), 
            ("iv", "is_video"), 
            ("last_time", "last_time"), 
            ("m", "is_mark"), 
            ("m", "star"), 
            ("ns", "name_show"), 
            ("p", "has_pass"), 
            ("play_long", "play_long"), 
            ("played_end", "played_end"), 
            ("pt", "pick_time"), 
            ("score", "score"), 
            ("sh", "is_share"), 
            ("sta", "status"), 
            ("style", "style"), 
            ("u", "thumb"), 
        ):
            if key in info:
                attr[name] = try_parse_int(info[key])
        if vdi := info.get("vdi"):
            attr["defination"] = vdi
            match vdi:
                case 1:
                    attr["defination_str"] = "video-sd"
                case 2:
                    attr["defination_str"] = "video-hd"
                case 3:
                    attr["defination_str"] = "video-fhd"
                case 4:
                    attr["defination_str"] = "video-1080p"
                case 5:
                    attr["defination_str"] = "video-4k"
                case 100:
                    attr["defination_str"] = "video-origin"
                case _:
                    attr["defination_str"] = "video-sd"
    if is_dir:
        attr["type"] = 0
    elif info.get("iv") or "vdi" in info:
        attr["type"] = 4
    elif type_ := CLASS_TO_TYPE.get(attr.get("class", "")):
        attr["type"] = type_
    elif type_ := SUFFIX_TO_TYPE.get(splitext(attr["name"])[1].lower()):
        attr["type"] = type_
    else:
        attr["type"] = 99
    if keep_raw:
        attr["raw"] = info
    return attr


@overload
def normalize_attr_app(
    info: Mapping[str, Any], 
    /, 
    simple: bool = False, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: None = None, 
) -> dict[str, Any]:
    ...
@overload
def normalize_attr_app[D: dict[str, Any]](
    info: Mapping[str, Any], 
    /, 
    simple: bool = False, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: type[D], 
) -> D:
    ...
def normalize_attr_app[D: dict[str, Any]](
    info: Mapping[str, Any], 
    /, 
    simple: bool = False, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: None | type[D] = None, 
) -> dict[str, Any] | D:
    """翻译 ``P115Client.fs_files_app()`` 方法响应的文件信息数据，使之便于阅读

    :param info: 原始数据
    :param simple: 只提取少量必要字段 "is_dir", "id", "parent_id", "name", "sha1", "size", "pickcode", "is_collect", "ctime", "mtime", "type"
    :param keep_raw: 是否保留原始数据，如果为 True，则保存到 "raw" 字段
    :param default: 一些预设值，可被覆盖
    :param dict_cls: 字典类型

    :return: 翻译后的 dict 类型数据
    """
    if dict_cls is None:
        dict_cls = cast(type[D], dict)
    attr: dict[str, Any] = dict_cls()
    if default:
        attr.update(default)
    is_dir = attr["is_dir"] = info["fc"] == "0" # file_category
    attr["id"] = int(info["fid"])               # file_id
    attr["parent_id"] = int(info["pid"])        # parent_id
    attr["name"] = info["fn"]
    sha1 = attr["sha1"] = info.get("sha1") or ""
    attr["size"] = int(info.get("fs") or 0)
    if "pc" in info:
        attr["pickcode"] = info["pc"]
    if simple:
        if "ic" in info:
            attr["is_collect"] = int(info["ic"])
        if "uppt" in info:
            attr["ctime"] = int(info["uppt"])
        if "upt" in info:
            attr["mtime"] = int(info["upt"])
    else:
        if "pickcode" in attr:
            attr["pick_code"] = attr["pickcode"]
        attr["ico"] = info.get("ico", "folder" if attr["is_dir"] else "")
        if "thumb" in info:
            thumb = info["thumb"]
            if thumb.startswith("?"):
                thumb = f"https://imgjump.115.com{thumb}&size=0&sha1={sha1}"
            attr["thumb"] = thumb
        if "uppt" in info: # pptime
            attr["ctime"] = attr["user_ptime"] = int(info["uppt"])
        if "upt" in info: # ptime
            attr["mtime"] = attr["user_utime"] = int(info["upt"])
        if "uet" in info: # utime
            attr["utime"] = int(info["uet"])
        for key, name in (
            ("aid", "area_id"),           # 域 id，表示文件的状态：1:正常 7:删除(回收站) 120:彻底删除
            ("all_skip_login", "all_skip_login"), # 是否支持免登录下载
            ("audio_play_long", "audio_play_long"), # 音频长度
            ("current_time", "current_time"), # 视频当前播放位置（从头开始到此为第 `current_time` 秒）
            ("d_img", "d_img"),           # 目录封面
            ("def", "defination"),        # 视频清晰度：1:标清 2:高清 3:超清 4:1080P 5:4k 100:原画
            ("def2", "defination2"),      # 视频清晰度：1:标清 2:高清 3:超清 4:1080P 5:4k 100:原画
            ("fatr", "audio_play_long"),  # 音频长度
            ("fco", "cover"),             # 目录封面
            ("fco", "folder_cover"),      # 目录封面
            ("fdesc", "desc"),            # 文件备注
            ("fl", "labels"),             # 文件标签，得到 1 个字典列表
            ("flabel", "fflabel"),        # 文件标签（一般为空）
            ("fta", "status"),            # 文件状态：0/2:未上传完成，1:已上传完成
            ("ftype", "file_type"),       # 文件类型代码
            ("ic", "is_collect"),         # 是否违规
            ("is_skip_login", "is_skip_login"), # 是否开启免登录下载
            ("is_top", "is_top"),         # 是否置顶
            ("ism", "is_mark"),           # 是否星标
            ("ism", "star"),              # 是否星标（别名）
            ("isp", "is_private"),        # 是否加密隐藏（隐藏模式中显示）
            ("ispl", "show_play_long"),   # 是否统计目录下视频时长
            ("iss", "is_share"),          # 是否共享
            ("issct", "is_shortcut"),     # 是否在快捷入口
            ("isv", "is_video"),          # 是否为视频
            ("last_time", "last_time"),   # 视频上次播放时间戳（秒）
            ("muc", "cover"),             # 封面
            ("muc", "music_cover"),       # 音乐封面
            ("multitrack", "multitrack"), # 音轨数量 
            ("play_long", "play_long"),   # 音视频时长
            ("played_end", "played_end"), # 是否播放完成
            ("unzip_status", "unzip_status"), # 解压状态：0(或无值):未解压或已完成 1:解压中
            ("uo", "source_url"),         # 原图地址
            ("v_img", "video_img_url"),   # 图片封面
        ):
            if key in info:
                attr[name] = try_parse_int(info[key])
    if is_dir:
        attr["type"] = 0
    elif (thumb := info.get("thumb")) and thumb.startswith("?"):
        attr["type"] = 2
    elif "muc" in info:
        attr["type"] = 3
    elif info.get("isv") or "def" in info or "def2" in info or "v_img" in info:
        attr["type"] = 4
    elif type_ := SUFFIX_TO_TYPE.get(splitext(attr["name"])[1].lower()):
        attr["type"] = type_
    else:
        attr["type"] = 99
    if keep_raw:
        attr["raw"] = info
    return attr


@overload
def normalize_attr_app2(
    info: Mapping[str, Any], 
    /, 
    simple: bool = False, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: None = None, 
) -> dict[str, Any]:
    ...
@overload
def normalize_attr_app2[D: dict[str, Any]](
    info: Mapping[str, Any], 
    /, 
    simple: bool = False, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: type[D], 
) -> D:
    ...
def normalize_attr_app2[D: dict[str, Any]](
    info: Mapping[str, Any], 
    /, 
    simple: bool = False, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: None | type[D] = None, 
) -> dict[str, Any] | D:
    """翻译 ``P115Client.fs_files_app2()`` 方法响应的文件信息数据，使之便于阅读

    :param info: 原始数据
    :param simple: 只提取少量必要字段 "is_dir", "id", "parent_id", "name", "sha1", "size", "pickcode", "is_collect", "ctime", "mtime", "type"
    :param keep_raw: 是否保留原始数据，如果为 True，则保存到 "raw" 字段
    :param default: 一些预设值，可被覆盖
    :param dict_cls: 字典类型

    :return: 翻译后的 dict 类型数据
    """
    if dict_cls is None:
        dict_cls = cast(type[D], dict)
    attr: dict[str, Any] = dict_cls()
    if default:
        attr.update(default)
    if "file_id" in info and "parent_id" in info:
        if "file_category" in info:
            is_dir = not int(info["file_category"])
        else:
            is_dir = bool(info.get("sha1") or info.get("file_sha1") or info.get("pick_code", "").startswith("f"))
        attr["id"] = int(info["file_id"])
        attr["parent_id"] = int(info["parent_id"])
        attr["name"] = info["file_name"]
    else:
        if is_dir := "file_id" not in info:
            attr["id"] = int(info["category_id"])
            attr["parent_id"] = int(info["parent_id"])
            attr["name"] = info["category_name"]
        else:
            attr["id"] = int(info["file_id"])
            attr["parent_id"] = int(info["category_id"])
            attr["name"] = info["file_name"]
    attr["is_dir"] = is_dir
    attr["sha1"] = info.get("sha1") or info.get("file_sha1") or ""
    attr["size"] = int(info.get("file_size") or 0)
    if "pick_code" in info:
        attr["pickcode"] = info["pick_code"]
    if simple:
        if "is_collect" in info:
            attr["is_collect"] = int(info["is_collect"])
        if "user_pptime" in info:
            attr["ctime"] = int(info["user_pptime"])
        if "user_ptime" in info:
            attr["mtime"] = int(info["user_ptime"])
    else:
        if "pickcode" in attr:
            attr["pick_code"] = attr["pickcode"]
        if is_dir:
            if "category_desc" in info:
                attr["desc"] = info["category_desc"]
            if "category_cover" in info:
                attr["cover"] = info["category_cover"]
        else:
            if "thumb_url" in info:
                attr["thumb"] = info["thumb_url"]
            if "file_description" in info:
                attr["desc"] = info["file_description"]
            if "file_tag" in info:
                attr["file_type"] = int(info["file_tag"])
            if "music_cover" in info:
                attr["cover"] = info["music_cover"]
        if "user_pptime" in info:
            attr["ctime"] = attr["user_ptime"] = int(info["user_pptime"])
        elif "pptime" in info:
            attr["ctime"] = attr["user_ptime"] = int(info["pptime"])
        if "user_ptime" in info:
            attr["mtime"] = attr["user_utime"] = int(info["user_ptime"])
        elif "ptime" in info:
            attr["mtime"] = attr["user_utime"] = int(info["ptime"])
        if "user_utime" in info:
            attr["utime"] = int(info["user_utime"])
        elif "utime" in info:
            attr["utime"] = int(info["utime"])
        attr["ico"] = info.get("ico", "folder" if attr["is_dir"] else "")
        if "fl" in info:
            attr["labels"] = info["fl"]
        for name in (
            "area_id", 
            "can_delete", 
            "cate_mark", 
            "category_file_count", 
            "category_order", 
            "current_time", 
            "d_img", 
            "definition", 
            "definition2", 
            "file_answer", 
            "file_category", 
            "file_eda", 
            "file_question", 
            "file_sort", 
            "file_status", 
            "has_desc", 
            "has_pass", 
            "is_collect", 
            "is_mark", 
            "is_private", 
            "is_share", 
            "is_top", 
            "is_video", 
            "last_time", 
            "password", 
            "pick_expire", 
            "pick_time", 
            "play_long", 
            "play_url", 
            "played_end", 
            "show_play_long", 
            "video_img_url", 
        ):
            if name in info:
                attr[name] = try_parse_int(info[name])
        if "is_mark" in attr:
            attr["star"] = attr["is_mark"]
    if is_dir:
        attr["type"] = 0
    elif "thumb_url" in info:
        attr["type"] = 2
    elif "music_cover" in info or "play_url" in info:
        attr["type"] = 3
    elif (
        info.get("is_video") or 
        "definition" in info or 
        "definition2" in info or 
        "video_img_url" in info
    ):
        attr["type"] = 4
    elif type_ := SUFFIX_TO_TYPE.get(splitext(attr["name"])[1].lower()):
        attr["type"] = type_
    else:
        attr["type"] = 99
    if keep_raw:
        attr["raw"] = info
    return attr


@overload
def normalize_attr(
    info: Mapping[str, Any], 
    /, 
    simple: bool = False, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: None = None, 
) -> AttrDict[str, Any]:
    ...
@overload
def normalize_attr[D: dict[str, Any]](
    info: Mapping[str, Any], 
    /, 
    simple: bool = False, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: type[D], 
) -> D:
    ...
def normalize_attr[D: dict[str, Any]](
    info: Mapping[str, Any], 
    /, 
    simple: bool = False, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: None | type[D] = None, 
) -> AttrDict[str, Any] | D:
    """翻译获取自罗列目录、搜索、获取文件信息等接口的数据，使之便于阅读

    :param info: 原始数据
    :param simple: 只提取少量必要字段 "is_dir", "id", "parent_id", "name", "sha1", "size", "pickcode", "is_collect", "ctime", "mtime"
    :param keep_raw: 是否保留原始数据，如果为 True，则保存到 "raw" 字段
    :param default: 一些预设值，可被覆盖
    :param dict_cls: 字典类型

    :return: 翻译后的 dict 类型数据
    """
    if "fn" in info:
        call = normalize_attr_app
    elif "file_id" in info or "category_id" in info:
        call = normalize_attr_app2
    else:
        call = normalize_attr_web
    if dict_cls is None:
        return call(info, simple=simple, keep_raw=keep_raw, default=default, dict_cls=AttrDict)
    else:
        return call(info, simple=simple, keep_raw=keep_raw, default=default, dict_cls=dict_cls)


@overload
def normalize_attr_simple(
    info: Mapping[str, Any], 
    /, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: None = None, 
) -> AttrDict[str, Any]:
    ...
@overload
def normalize_attr_simple[D: dict[str, Any]](
    info: Mapping[str, Any], 
    /, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: type[D], 
) -> D:
    ...
def normalize_attr_simple[D: dict[str, Any]](
    info: Mapping[str, Any], 
    /, 
    keep_raw: bool = False, 
    default: None | Mapping[str, Any] | Iterable[tuple[str, Any]] = None, 
    *, 
    dict_cls: None | type[D] = None, 
) -> AttrDict[str, Any] | D:
    """翻译获取自罗列目录、搜索、获取文件信息等接口的数据，使之便于阅读

    .. note::
        只提取少量必要字段 "is_dir", "id", "parent_id", "name", "sha1", "size", "pickcode", "is_collect", "ctime", "mtime"

    :param info: 原始数据
    :param keep_raw: 是否保留原始数据，如果为 True，则保存到 "raw" 字段
    :param default: 一些预设值，可被覆盖
    :param dict_cls: 字典类型

    :return: 翻译后的 dict 类型数据
    """
    return normalize_attr(
        info, 
        simple=True, 
        keep_raw=keep_raw, 
        default=default, 
        dict_cls=dict_cls, 
    )


from .fs_files import iter_fs_files_serialized
from .iterdir import overview_attr, iterdir, share_iterdir, update_resp_ancestors


def type_of_attr(attr: str | Mapping, /) -> int:
    """推断文件信息所属类型（试验版，未必准确）

    .. note::
        如果直接传入文件名，则视为文件，在获取不到时，返回 99（如果你已知这是目录，你直接自己就能计作 0）

    :param attr: 文件名或文件信息

    :return: 返回类型代码

        - 0: 目录
        - 1: 文档
        - 2: 图片
        - 3: 音频
        - 4: 视频
        - 5: 压缩包
        - 6: 应用
        - 7: 书籍
        - 99: 其它文件
"""
    if not attr:
        return 0
    if isinstance(attr, str):
        suffix = splitext(attr)[1]
        if not suffix:
            return 99
        return SUFFIX_TO_TYPE.get(suffix, 99)
    if attr.get("is_dir"):
        return 0
    type: None | int
    if type := CLASS_TO_TYPE.get(attr.get("class", "")):
        return type
    if type := SUFFIX_TO_TYPE.get(splitext(attr["name"])[1].lower()):
        return type
    if attr.get("is_video") or "defination" in attr:
        return 4
    return 99


@overload
def get_attr(
    client: str | PathLike | P115Client, 
    id: int | str = 0, 
    skim: bool = False, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def get_attr(
    client: str | PathLike | P115Client, 
    id: int | str = 0, 
    skim: bool = False, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def get_attr(
    client: str | PathLike | P115Client, 
    id: int | str = 0, 
    skim: bool = False, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """获取文件或目录的信息

    :param client: 115 客户端或 cookies
    :param id: 文件或目录的 id 或 pickcode
    :param skim: 是否获取简要信息（可避免风控）
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 文件或目录的信息
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    id = to_id(id)
    def gen_step():
        from dictattr import AttrDict
        if skim:
            if not id:
                return {
                    "id": 0, 
                    "name": "", 
                    "pickcode": "", 
                    "sha1": "", 
                    "size": 0, 
                    "is_dir": True, 
                }
            resp = yield client.fs_file_skim(id, async_=async_, **request_kwargs)
            check_response(resp)
            info = resp["data"][0]
            return AttrDict(
                id=int(info["file_id"]), 
                name=unescape_115_charref(info["file_name"]), 
                pickcode=info["pick_code"], 
                sha1=info["sha1"], 
                size=int(info["file_size"]), 
                is_dir=not info["sha1"], 
            )
        else:
            if not id:
                return {
                    "is_dir": True,
                    "id": 0, 
                    "parent_id": 0, 
                    "name": "", 
                    "sha1": "", 
                    "size": 0, 
                    "pickcode": "", 
                    "pick_code": "", 
                    "ico": "folder", 
                    "mtime": 0, 
                    "user_utime": 0, 
                    "ctime": 0, 
                    "user_ptime": 0, 
                    "atime": 0, 
                    "user_otime": 0, 
                    "utime": 0, 
                    "time": 0, 
                    "has_desc": 0, 
                    "area_id": 1, 
                    "cover": "", 
                    "category_cover": "", 
                    "pick_expire": "", 
                    "labels": [], 
                    "is_private": 0, 
                    "is_top": 0, 
                    "show_play_long": 0, 
                    "is_shortcut": 0, 
                    "is_mark": 0, 
                    "star": 0, 
                    "score": 0, 
                    "is_share": 0, 
                    "thumb": "", 
                    "type": 0, 
                }
            resp = yield client.fs_file(id, async_=async_, **request_kwargs)
            check_response(resp)
            return normalize_attr_web(resp["data"][0], dict_cls=AttrDict)
    return run_gen_step(gen_step, async_)


@overload
def get_info(
    client: str | PathLike | P115Client | P115OpenClient, 
    id: int | str = 0, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> dict:
    ...
@overload
def get_info(
    client: str | PathLike | P115Client | P115OpenClient, 
    id: int | str = 0, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, dict]:
    ...
def get_info(
    client: str | PathLike | P115Client | P115OpenClient, 
    id: int | str = 0, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> dict | Coroutine[Any, Any, dict]:
    """获取文件或目录的信息

    .. caution::
        如果是目录，还包含其内（子目录树下）所有的文件数和目录数，数量越多，响应越久，所以对于目录要慎用

    :param client: 115 客户端或 cookies
    :param id: 文件或目录的 id 或 pickcode
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 文件或目录的信息
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if id_to_dirnode is None:
        id_to_dirnode = ID_TO_DIRNODE_CACHE[client.user_id]
    try:
        id = to_id(id)
    except ValueError:
        if isinstance(client, P115Client) and app != "open":
            raise
    def gen_step():
        if not isinstance(client, P115Client) or app == "open":
            resp = yield client.fs_info_open(
                id, 
                async_=async_, 
                **request_kwargs, 
            )
        elif app in ("", "web", "desktop", "harmony", "aps"):
            resp = yield client.fs_category_get(
                id, 
                async_=async_, 
                **request_kwargs, 
            )
        else:
            resp = yield client.fs_category_get_app(
                id, 
                app=app, 
                async_=async_, 
                **request_kwargs, 
            )
        return update_resp_ancestors(resp, id_to_dirnode, error=FileNotFoundError(errno.ENOENT, f"not found: {id!r}"))
    return run_gen_step(gen_step, async_)


@overload
def iter_list(
    client: str | PathLike | P115Client | P115OpenClient, 
    cid: int | str = 0, 
    start: int = 0, 
    page_size: int = 7_000, 
    first_page_size: int = 0, 
    payload: None | dict = None, 
    normalize_attr: None | Callable[[dict], dict] = normalize_attr, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> Iterator[dict]:
    ...
@overload
def iter_list(
    client: str | PathLike | P115Client | P115OpenClient, 
    cid: int | str = 0, 
    start: int = 0, 
    page_size: int = 7_000, 
    first_page_size: int = 0, 
    payload: None | dict = None, 
    normalize_attr: None | Callable[[dict], dict] = normalize_attr, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> AsyncIterator[dict]:
    ...
def iter_list(
    client: str | PathLike | P115Client | P115OpenClient, 
    cid: int | str = 0, 
    start: int = 0, 
    page_size: int = 7_000, 
    first_page_size: int = 0, 
    payload: None | dict = None, 
    normalize_attr: None | Callable[[dict], dict] = normalize_attr, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> Iterator[dict] | AsyncIterator[dict]:
    """在某个目录下面，迭代获取直属的文件或目录列表（逐页拉取）

    :param client: 115 客户端或 cookies
    :param cid: 目录的 id 或 pickcode
    :param start: 开始索引（从 0 开始）
    :param page_size: 分页大小，如果 <= 0，则自动确定
    :param first_page_size: 首次拉取的分页大小，如果 <= 0，则自动确定
    :param payload: 其它的查询参数
    :param normalize_attr: 把数据进行转换处理，使之便于阅读
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 迭代器，每迭代一次执行一次分页拉取请求（就像瀑布流）
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if id_to_dirnode is None:
        id_to_dirnode = ID_TO_DIRNODE_CACHE[client.user_id]
    cid = to_id(cid)
    def gen_step():
        with with_iter_next(iter_fs_files_serialized(
            client, 
            dict(payload or (), cid=cid, offset=start), 
            page_size=page_size, 
            first_page_size=first_page_size, 
            app=app, 
            async_=async_, 
            **request_kwargs, 
        )) as get_next:
            while True:
                resp = yield get_next()
                update_resp_ancestors(resp, id_to_dirnode, error=FileNotFoundError(errno.ENOENT, f"not found: {cid!r}"))
                if id_to_dirnode is not ...:
                    for attr in filter(attrgetter("is_dir"), map(overview_attr, resp["data"])):
                        id_to_dirnode[attr.id] = (attr.name, attr.parent_id)
                if normalize_attr:
                    resp["data"] = list(map(normalize_attr, resp["data"]))
                yield Yield(resp)
    return run_gen_step_iter(gen_step, async_)


@overload
def get_ancestors(
    client: str | PathLike | P115Client | P115OpenClient, 
    attr: int | str | dict = 0, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    ensure_file: None | bool = None, 
    refresh: bool = False, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> list[dict]:
    ...
@overload
def get_ancestors(
    client: str | PathLike | P115Client | P115OpenClient, 
    attr: int | str | dict = 0, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    ensure_file: None | bool = None, 
    refresh: bool = False, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, list[dict]]:
    ...
def get_ancestors(
    client: str | PathLike | P115Client | P115OpenClient, 
    attr: int | str | dict = 0, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    ensure_file: None | bool = None, 
    refresh: bool = False, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> list[dict] | Coroutine[Any, Any, list[dict]]:
    """获取某个节点对应的祖先节点列表（只有 "id"、"parent_id" 和 "name" 的信息）

    :param client: 115 客户端或 cookies
    :param attr: 待查询节点 id 或 pickcode 或信息字典（必须有 "id"，可选有 "parent_id" 或 "is_dir"）
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param ensure_file: 是否确保为文件

        - True:  确定是文件
        - False: 确定是目录
        - None:  不确定

    :param refresh: 是否强制刷新，如果为 False，则尽量从 ``id_to_dirnode`` 获取，以减少接口调用
    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 目录所对应的祖先信息列表，每一条的结构如下

        .. code:: python

            {
                "id": int, # 目录的 id
                "parent_id": int, # 上级目录的 id
                "name": str, # 名字
            }
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if id_to_dirnode is None:
        id_to_dirnode = ID_TO_DIRNODE_CACHE[client.user_id]
    def get_resp_by_info(id: int, /):
        return get_info(
            client, 
            id, 
            id_to_dirnode=id_to_dirnode, 
            app=app, 
            async_=async_, 
            **request_kwargs, 
        )
    do_next: Callable = anext if async_ else next
    def get_resp_by_list(cid: int, /):
        return do_next(iter_list(
            client, 
            cid, 
            page_size=1, 
            payload={"cur": 1, "nf": 1, "star": 1, "hide_data": 1}, 
            id_to_dirnode=id_to_dirnode, 
            normalize_attr=None, 
            app=app, 
            async_=async_, 
            **request_kwargs, 
        ))
    def get_resp(id: int, /, ensure_file: None | bool = None):
        if ensure_file is None:
            try:
                return get_resp_by_list(id)
            except (FileNotFoundError, NotADirectoryError):
                return get_resp_by_info(id)
        elif ensure_file:
            return get_resp_by_info(id)
        else:
            return get_resp_by_list(id)
    def gen_step():
        nonlocal attr, ensure_file
        ancestors: list[dict] = [{"id": 0, "parent_id": 0, "name": ""}]
        if not attr:
            return ancestors
        if isinstance(attr, dict):
            if not (fid := int(attr["id"])):
                return ancestors
            is_dir: None | bool = attr.get("is_dir")
            if is_dir is None:
                if "parent_id" in attr:
                    pid = int(attr["parent_id"])
                    ancestors = yield get_ancestors(
                        client, 
                        pid, 
                        id_to_dirnode=id_to_dirnode, 
                        ensure_file=False, 
                        refresh=refresh, 
                        app=app, 
                        async_=async_, 
                        **request_kwargs, 
                    )
                    name = ""
                    if "name" in attr:
                        name = attr["name"]
                    elif isinstance(client, P115Client):
                        attr = yield get_attr(
                            client, 
                            fid, 
                            skim=True, 
                            async_=async_, 
                            **request_kwargs, 
                        )
                        name = cast(dict, attr)["name"]
                    if name:
                        ancestors.append({"id": fid, "parent_id": pid, "name": name})
                        return ancestors
            else:
                ensure_file = not is_dir
        elif not (fid := to_id(attr)):
            return ancestors
        if not refresh and id_to_dirnode is not ... and fid in id_to_dirnode:
            parts: list[dict] = []
            add_part = parts.append
            try:
                cid = fid
                while cid:
                    id = cid
                    name, cid = id_to_dirnode[cid]
                    add_part({"id": id, "name": name, "parent_id": cid})
                ancestors.extend(reversed(parts))
                return ancestors
            except KeyError:
                pass
        resp = yield get_resp(fid, ensure_file)
        return resp["ancestors"]
    return run_gen_step(gen_step, async_)


@overload
def get_path(
    client: str | PathLike | P115Client | P115OpenClient, 
    attr: int | str | dict = 0, 
    root_id: None | int | str = None, 
    escape: None | bool | Callable[[str], str] = True, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    ensure_file: None | bool = None, 
    refresh: bool = False, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> str:
    ...
@overload
def get_path(
    client: str | PathLike | P115Client | P115OpenClient, 
    attr: int | str | dict = 0, 
    root_id: None | int | str = None, 
    escape: None | bool | Callable[[str], str] = True, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    ensure_file: None | bool = None, 
    refresh: bool = False, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, str]:
    ...
def get_path(
    client: str | PathLike | P115Client | P115OpenClient, 
    attr: int | str | dict = 0, 
    root_id: None | int | str = None, 
    escape: None | bool | Callable[[str], str] = True, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    ensure_file: None | bool = None, 
    refresh: bool = False, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> str | Coroutine[Any, Any, str]:
    """获取目录对应的路径（绝对路径或相对路径）

    :param client: 115 客户端或 cookies
    :param attr: 待查询节点 id 或 pickcode 或信息字典（必须有 "id"，可选有 "parent_id" 或 "is_dir"）
    :param root_id: 根目录 id 或 pickcode，如果指定此参数且不为 None，则返回相对路径，否则返回绝对路径
    :param escape: 对文件名进行转义

        - 如果为 None，则不处理；否则，这个函数用来对文件名中某些符号进行转义，例如 "/" 等
        - 如果为 True，则使用 `posixpatht.escape`，会对文件名中 "/"，或单独出现的 "." 和 ".." 用 "\\" 进行转义
        - 如果为 False，则使用 `posix_escape_name` 函数对名字进行转义，会把文件名中的 "/" 转换为 "|"
        - 如果为 Callable，则用你所提供的调用，以或者转义后的名字

    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param ensure_file: 是否确保为文件

        - True:  确定是文件
        - False: 确定是目录
        - None:  不确定

    :param refresh: 是否刷新。如果为 True，则会执行网络请求以查询；如果为 False，则直接从 `id_to_dirnode` 中获取
    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 目录对应的绝对路径或相对路径
    """
    if isinstance(escape, bool):
        if escape:
            from posixpatht import escape
        else:
            escape = posix_escape_name
    escape = cast(None | Callable[[str], str], escape)
    if root_id is not None:
        root_id = to_id(root_id)
    def gen_step():
        if root_id is not None and (
            not attr or 
            (int(attr["id"]) if isinstance(attr, dict) else to_id(attr)) == root_id
        ):
            return ""
        ancestors = yield get_ancestors(
            client, 
            attr, 
            id_to_dirnode=id_to_dirnode, 
            ensure_file=ensure_file, 
            refresh=refresh, 
            app=app, 
            async_=async_, # type: ignore
            **request_kwargs, 
        )
        if root_id is None:
            parts = (a["name"] for a in ancestors)
        elif ancestors[0]["id"] == root_id:
            parts = (a["name"] for a in ancestors[1:])
        else:
            parts = (a["name"] for a in dropwhile(lambda a: a["parent_id"] != root_id, ancestors))
        if escape is None:
            return "/".join(parts)
        else:
            return "/".join(map(escape, parts))
    return run_gen_step(gen_step, async_)


@overload
def get_id(
    client: str | PathLike | P115Client | P115OpenClient, 
    id: int = -1, 
    pickcode: str = "", 
    sha1: str = "", 
    name: str = "", 
    path: str | Sequence[str] = "", 
    value: int | str | Sequence[str] = "", 
    size: int = -1, 
    cid: int = 0, 
    ensure_file: None | bool = None, 
    is_posixpath: bool = False, 
    refresh: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    dont_use_getid: bool = False, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> int:
    ...
@overload
def get_id(
    client: str | PathLike | P115Client | P115OpenClient, 
    id: int = -1, 
    pickcode: str = "", 
    sha1: str = "", 
    name: str = "", 
    path: str | Sequence[str] = "", 
    value: int | str | Sequence[str] = "", 
    size: int = -1, 
    cid: int = 0, 
    ensure_file: None | bool = None, 
    is_posixpath: bool = False, 
    refresh: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    dont_use_getid: bool = False, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, int]:
    ...
def get_id(
    client: str | PathLike | P115Client | P115OpenClient, 
    id: int = -1, 
    pickcode: str = "", 
    sha1: str = "", 
    name: str = "", 
    path: str | Sequence[str] = "", 
    value: int | str | Sequence[str] = "", 
    size: int = -1, 
    cid: int = 0, 
    ensure_file: None | bool = None, 
    is_posixpath: bool = False, 
    refresh: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    dont_use_getid: bool = False, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> int | Coroutine[Any, Any, int]:
    """获取 id

    .. note::
        优先级，``id > pickcode > name > path > value``

    :param client: 115 客户端或 cookies
    :param id: id
    :param pickcode: 提取码
    :param sha1: 文件的 sha1 散列值
    :param name: 名称
    :param path: 路径
    :param value: 当 ``id``、``pickcode``、``name`` 和 ``path`` 不可用时生效，将会自动决定所属类型
    :param size: 文件大小
    :param cid: 顶层目录 id
    :param ensure_file: 是否确保为文件

        - True: 必须是文件
        - False: 必须是目录
        - None: 可以是目录或文件

    :param is_posixpath: 使用 posixpath，会把 "/" 转换为 "|"，因此解析的时候，会对 "|" 进行特别处理
    :param refresh: 是否刷新。如果为 True，则会执行网络请求以查询；如果为 False，则直接从 `id_to_dirnode` 中获取
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param app: 使用指定 app（设备）的接口
    :param dont_use_getid: 不要使用 `client.fs_dir_getid` 或 `client.fs_dir_getid_app`，以便 `id_to_dirnode` 有缓存
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 文件或目录的 id
    """
    if id >= 0:
        if id or not ensure_file:
            return id
    if pickcode:
        return to_id(pickcode)
    elif sha1:
        return get_id_to_sha1(
            client, 
            sha1=sha1, 
            size=size, 
            cid=cid, 
            app=app, 
            async_=async_, 
            **request_kwargs, 
        )
    elif name:
        return get_id_to_name(
            client, 
            name=name, 
            size=size, 
            cid=cid, 
            ensure_file=ensure_file, 
            app=app, 
            async_=async_, 
            **request_kwargs, 
        )
    elif path:
        return get_id_to_path(
            client, 
            path=path, 
            cid=cid, 
            ensure_file=ensure_file, 
            is_posixpath=is_posixpath, 
            refresh=refresh, 
            id_to_dirnode=id_to_dirnode, 
            app=app, 
            dont_use_getid=dont_use_getid, 
            async_=async_, 
            **request_kwargs, 
        )
    else:
        if isinstance(value, (int, str)):
            if is_valid_id(value):
                id = int(value)
                if id or not ensure_file:
                    return id
                value = str(id)
            value = cast(str, value)
            if is_valid_pickcode(value):
                return to_id(value)
            elif is_valid_sha1(value):
                return get_id_to_sha1(
                    client, 
                    sha1=value, 
                    size=size, 
                    cid=cid, 
                    app=app, 
                    async_=async_, 
                    **request_kwargs, 
                )
            elif is_valid_name(value):
                return get_id_to_name(
                    client, 
                    name=value, 
                    size=size, 
                    cid=cid, 
                    ensure_file=ensure_file, 
                    app=app, 
                    async_=async_, 
                    **request_kwargs, 
                )
        return get_id_to_path(
            client, 
            path=value, 
            cid=cid, 
            ensure_file=ensure_file, 
            is_posixpath=is_posixpath, 
            refresh=refresh, 
            id_to_dirnode=id_to_dirnode, 
            app=app, 
            dont_use_getid=dont_use_getid, 
            async_=async_, 
            **request_kwargs, 
        )


@overload
def get_id_to_path(
    client: str | PathLike | P115Client | P115OpenClient, 
    path: str | Sequence[str], 
    cid: int = 0, 
    ensure_file: None | bool = None, 
    is_posixpath: bool = False, 
    refresh: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    dont_use_getid: bool = False, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> int:
    ...
@overload
def get_id_to_path(
    client: str | PathLike | P115Client | P115OpenClient, 
    path: str | Sequence[str], 
    cid: int = 0, 
    ensure_file: None | bool = None, 
    is_posixpath: bool = False, 
    refresh: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    dont_use_getid: bool = False, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, int]:
    ...
def get_id_to_path(
    client: str | PathLike | P115Client | P115OpenClient, 
    path: str | Sequence[str], 
    cid: int = 0, 
    ensure_file: None | bool = None, 
    is_posixpath: bool = False, 
    refresh: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    dont_use_getid: bool = False, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> int | Coroutine[Any, Any, int]:
    """获取 path 对应的 id

    :param client: 115 客户端或 cookies
    :param path: 路径
    :param cid: 顶层目录的 id
    :param ensure_file: 是否确保为文件

        - True: 必须是文件
        - False: 必须是目录
        - None: 可以是目录或文件

    :param is_posixpath: 使用 posixpath，会把 "/" 转换为 "|"，因此解析的时候，会对 "|" 进行特别处理
    :param refresh: 是否刷新。如果为 True，则会执行网络请求以查询；如果为 False，则直接从 `id_to_dirnode` 中获取
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param app: 使用指定 app（设备）的接口
    :param dont_use_getid: 不要使用 `client.fs_dir_getid` 或 `client.fs_dir_getid_app`，以便 `id_to_dirnode` 有缓存
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 文件或目录的 id
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    if id_to_dirnode is None:
        id_to_dirnode = ID_TO_DIRNODE_CACHE[client.user_id]
    error = FileNotFoundError(errno.ENOENT, f"no such path: {path!r}")
    def gen_step():
        nonlocal ensure_file, cid, path
        if isinstance(path, str):
            if path.startswith("/"):
                cid = 0
            if path in (".", "..", "/"):
                if ensure_file:
                    raise error
                return cid
            elif path.startswith("根目录 > "):
                cid = 0
                patht = path.split(" > ")[1:]
            elif is_posixpath:
                if ensure_file is None and path.endswith("/"):
                    ensure_file = False
                patht = [p for p in path.split("/") if p]
            else:
                if ensure_file is None and path_is_dir_form(path):
                    ensure_file = False
                patht, _ = splits(path.lstrip("/"))
        else:
            if path and not path[0]:
                cid = 0
                patht = list(path[1:])
            else:
                patht = [p for p in path if p]
            if not patht:
                return cid
        if not patht:
            if ensure_file:
                raise error
            return cid
        if not isinstance(client, P115Client) or app == "open":
            resp = yield get_info(
                client, 
                ">" + ">".join(patht), 
                id_to_dirnode=id_to_dirnode, 
                app="open", 
                async_=async_, 
                **request_kwargs, 
            )
            return P115ID(resp["id"], resp, about="path")
        i = 0
        start_parent_id = cid
        if not refresh and id_to_dirnode and id_to_dirnode is not ...:
            if i := len(patht) - bool(ensure_file):
                obj = "|" if is_posixpath else "/"
                for i in range(i):
                    if obj in patht[i]:
                        break
                else:
                    i += 1
            if i:
                for i in range(i):
                    needle = (patht[i], cid)
                    for fid, key in id_to_dirnode.items():
                        if needle == key:
                            cid = fid
                            break
                    else:
                        break
                else:
                    i += 1
        if i == len(patht):
            return cid
        if not start_parent_id:
            stop = 0
            if j := len(patht) - bool(ensure_file):
                for stop, part in enumerate(patht[:j]):
                    if "/" in part:
                        break
                else:
                    stop += 1
            if not dont_use_getid:
                while stop > i:
                    if app in ("", "web", "desktop", "harmony", "aps"):
                        fs_dir_getid: Callable = client.fs_dir_getid
                    else:
                        fs_dir_getid = partial(client.fs_dir_getid_app, app=app)
                    dirname = "/".join(patht[:stop])
                    resp = yield fs_dir_getid(dirname, async_=async_, **request_kwargs)
                    check_response(resp)
                    pid = int(resp["id"])
                    if not pid:
                        if stop == len(patht) and ensure_file is None:
                            stop -= 1
                            continue
                        raise error
                    cid = pid
                    i = stop
                    break
        if i == len(patht):
            return cid
        for name in patht[i:-1]:
            if is_posixpath:
                name = name.replace("/", "|")
            with with_iter_next(iterdir(
                client, 
                cid, 
                ensure_file=False, 
                app=app, 
                id_to_dirnode=id_to_dirnode, 
                async_=async_, 
                **request_kwargs, 
            )) as get_next:
                found = False
                while not found:
                    attr = yield get_next()
                    found = (attr["name"].replace("/", "|") if is_posixpath else attr["name"]) == name
                    cid = attr["id"]
                if not found:
                    raise error
        name = patht[-1]
        if is_posixpath:
            name = name.replace("/", "|")
        with with_iter_next(iterdir(
            client, 
            cid, 
            app=app, 
            id_to_dirnode=id_to_dirnode, 
            async_=async_, 
            **request_kwargs, 
        )) as get_next:
            while True:
                attr = yield get_next()
                if (attr["name"].replace("/", "|") if is_posixpath else attr["name"]) == name:
                    if ensure_file is None or ensure_file ^ attr["is_dir"]:
                        return P115ID(attr["id"], attr, about="path",)
        raise error
    return run_gen_step(gen_step, async_)


@overload
def get_id_to_sha1(
    client: str | PathLike | P115Client | P115OpenClient, 
    sha1: str, 
    size: int = -1, 
    cid: int | str = 0, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> P115ID:
    ...
@overload
def get_id_to_sha1(
    client: str | PathLike | P115Client | P115OpenClient, 
    sha1: str, 
    size: int = -1, 
    cid: int | str = 0, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, P115ID]:
    ...
def get_id_to_sha1(
    client: str | PathLike | P115Client | P115OpenClient, 
    sha1: str, 
    size: int = -1, 
    cid: int | str = 0, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> P115ID | Coroutine[Any, Any, P115ID]:
    """获取 sha1 对应的文件的 id

    .. caution::
        这个函数并不会检查输入的 ``sha1`` 是否合法

    :param client: 115 客户端或 cookies
    :param sha1: 文件的 sha1 哈希值
    :param size: 文件大小
    :param cid: 顶层目录 id
    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 文件或目录的 id
    """
    sha1 = sha1.upper()
    assert size or sha1 == "DA39A3EE5E6B4B0D3255BFEF95601890AFD80709"
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    def gen_step():
        search: None | Callable = None
        if not isinstance(client, P115Client) or app == "open":
            search = client.fs_search_open
        elif app in ("", "web", "desktop", "harmony", "aps"):
            if not cid and size < 0:
                resp: dict = yield client.fs_shasearch(sha1, async_=async_, **request_kwargs)
                check_response(resp)
                attr = normalize_attr(resp["data"])
                return P115ID(attr["id"], attr, about="sha1", sha1=sha1)
            else:
                search = client.fs_search
        else:
            search = partial(client.fs_search_app, app=app)
        if search is not None:
            payload = {"cid": cid, "fc": 0, "limit": 100, "search_value": sha1}
            for offset in range(0, 10_000, 100):
                if offset and resp["count"] <= offset:
                    break
                payload["offset"] = offset
                resp = yield search(payload, async_=async_, **request_kwargs)
                check_response(resp)
                for attr in map(normalize_attr, resp["data"]):
                    if attr["sha1"] != sha1:
                        break
                    if size < 0 or attr["size"] == size:
                        return P115ID(attr["id"], attr, about="sha1", sha1=sha1)
        throw(
            errno.ENOENT, 
            {"state": False, "user_id": client.user_id, "sha1": sha1, "size": size, "cid": cid, "error": "not found"}, 
        )
    return run_gen_step(gen_step, async_)


@overload
def get_id_to_name(
    client: str | PathLike | P115Client | P115OpenClient, 
    name: str, 
    size: int = -1, 
    cid: int | str = 0, 
    ensure_file: None | bool = None, 
    app: str = "web", 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> P115ID:
    ...
@overload
def get_id_to_name(
    client: str | PathLike | P115Client | P115OpenClient, 
    name: str, 
    size: int = -1, 
    cid: int | str = 0, 
    ensure_file: None | bool = None, 
    app: str = "web", 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, P115ID]:
    ...
def get_id_to_name(
    client: str | PathLike | P115Client | P115OpenClient, 
    name: str, 
    size: int = -1, 
    cid: int | str = 0, 
    ensure_file: None | bool = None, 
    app: str = "web", 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> P115ID | Coroutine[Any, Any, P115ID]:
    """获取 name 对应的文件的 id

    .. caution::
        这个函数并不会检查输入的 ``name`` 是否合法

    :param client: 115 客户端或 cookies
    :param name: 文件名
    :param size: 文件大小
    :param cid: 顶层目录 id
    :param ensure_file: 是否确保为文件

        - True:  确定是文件
        - False: 确定是目录
        - None:  不确定

    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 文件或目录的 id
    """
    assert name
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    def gen_step():
        if not isinstance(client, P115Client) or app == "open":
            search: Callable = client.fs_search_open
        elif app in ("", "web", "desktop", "harmony", "aps"):
            search = client.fs_search
        else:
            search = partial(client.fs_search_app, app=app)
        payload = {"cid": cid, "limit": 10_000, "search_value": name}
        if ensure_file:
            payload["fc"] = 0
            suffix = name.rpartition(".")[-1]
            if suffix.isalnum():
                payload["suffix"] = suffix
        elif ensure_file is False:
            payload["fc"] = 1
        resp: dict = yield search(payload, async_=async_, **request_kwargs)
        if ensure_file and get_first(resp, "errno", "errNo", default=0) == 20021:
            payload.pop("suffix")
            resp = yield search(payload, async_=async_, **request_kwargs)
        check_response(resp)
        for attr in map(normalize_attr, resp["data"]):
            if attr["name"] == name and (
                not ensure_file or 
                size < 0 or 
                attr["size"] == size
            ):
                return P115ID(attr["id"], attr, about="name", name=name)
        throw(
            errno.ENOENT, 
            {"state": False, "user_id": client.user_id, "name": name, "size": size, "cid": cid, "error": "not found"}, 
        )
    return run_gen_step(gen_step, async_)


@overload
def share_get_id(
    client: str | PathLike | P115Client, 
    share_code: str, 
    receive_code: str = "", 
    id: int = -1, 
    name: str = "", 
    path: str | Sequence[str] = "", 
    value: int | str | Sequence[str] = "", 
    size: int = -1, 
    cid: int = 0, 
    ensure_file: None | bool = None, 
    is_posixpath: bool = False,
    refresh: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> int:
    ...
@overload
def share_get_id(
    client: str | PathLike | P115Client, 
    share_code: str, 
    receive_code: str = "", 
    id: int = -1, 
    name: str = "", 
    path: str | Sequence[str] = "", 
    value: int | str | Sequence[str] = "", 
    size: int = -1, 
    cid: int = 0, 
    ensure_file: None | bool = None, 
    is_posixpath: bool = False,
    refresh: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, int]:
    ...
def share_get_id(
    client: str | PathLike | P115Client, 
    share_code: str, 
    receive_code: str = "", 
    id: int = -1, 
    name: str = "", 
    path: str | Sequence[str] = "", 
    value: int | str | Sequence[str] = "", 
    size: int = -1, 
    cid: int = 0, 
    ensure_file: None | bool = None, 
    is_posixpath: bool = False,
    refresh: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> int | Coroutine[Any, Any, int]:
    """对分享链接，获取 id

    .. note::
        优先级，``name > path > value``

    :param client: 115 客户端或 cookies
    :param share_code: 分享码或链接
    :param receive_code: 接收码
    :param id: id
    :param name: 名称
    :param path: 路径
    :param value: 当 ``id``、``name`` 和 ``path`` 不可用时生效，将会自动决定所属类型
    :param size: 文件大小
    :param cid: 顶层目录 id
    :param ensure_file: 是否确保为文件

        - True: 必须是文件
        - False: 必须是目录
        - None: 可以是目录或文件

    :param is_posixpath: 使用 posixpath，会把 "/" 转换为 "|"，因此解析的时候，会对 "|" 进行特别处理
    :param refresh: 是否刷新。如果为 True，则会执行网络请求以查询；如果为 False，则直接从 `id_to_dirnode` 中获取
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 文件或目录的 id
    """
    if id >= 0:
        if id or not ensure_file:
            return id
    if name:
        return share_get_id_to_name(
            client, 
            name=name, 
            share_code=share_code, 
            receive_code=receive_code, 
            size=size, 
            cid=cid, 
            ensure_file=ensure_file, 
            async_=async_, 
            **request_kwargs, 
        )
    elif path:
        return share_get_id_to_path(
            client, 
            path=path, 
            share_code=share_code, 
            receive_code=receive_code, 
            cid=cid, 
            ensure_file=ensure_file, 
            is_posixpath=is_posixpath, 
            refresh=refresh, 
            id_to_dirnode=id_to_dirnode, 
            async_=async_, 
            **request_kwargs, 
        )
    else:
        if isinstance(value, (int, str)):
            if is_valid_id(value):
                id = int(value)
                if id or not ensure_file:
                    return id
                value = str(id)
            value = cast(str, value)
            if is_valid_name(value):
                return share_get_id_to_name(
                    client, 
                    name=value, 
                    share_code=share_code, 
                    receive_code=receive_code, 
                    size=size, 
                    cid=cid, 
                    ensure_file=ensure_file, 
                    async_=async_, 
                    **request_kwargs, 
                )
        return share_get_id_to_path(
            client, 
            path=value, 
            share_code=share_code, 
            receive_code=receive_code, 
            cid=cid, 
            ensure_file=ensure_file, 
            is_posixpath=is_posixpath, 
            refresh=refresh, 
            id_to_dirnode=id_to_dirnode, 
            async_=async_, 
            **request_kwargs, 
        )


@overload
def share_get_id_to_path(
    client: str | PathLike | P115Client, 
    share_code: str, 
    receive_code: str = "", 
    path: str | Sequence[str] = "", 
    cid: int = 0, 
    ensure_file: None | bool = None, 
    is_posixpath: bool = False, 
    refresh: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> int:
    ...
@overload
def share_get_id_to_path(
    client: str | PathLike | P115Client, 
    share_code: str, 
    receive_code: str = "", 
    path: str | Sequence[str] = "", 
    cid: int = 0, 
    ensure_file: None | bool = None, 
    is_posixpath: bool = False, 
    refresh: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, int]:
    ...
def share_get_id_to_path(
    client: str | PathLike | P115Client, 
    share_code: str, 
    receive_code: str = "", 
    path: str | Sequence[str] = "", 
    cid: int = 0, 
    ensure_file: None | bool = None, 
    is_posixpath: bool = False, 
    refresh: bool = False, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> int | Coroutine[Any, Any, int]:
    """对分享链接，获取 path 对应的 id

    :param client: 115 客户端或 cookies
    :param share_code: 分享码或链接
    :param receive_code: 接收码
    :param path: 路径
    :param cid: 顶层目录的 id
    :param ensure_file: 是否确保为文件

        - True: 必须是文件
        - False: 必须是目录
        - None: 可以是目录或文件

    :param is_posixpath: 使用 posixpath，会把 "/" 转换为 "|"，因此解析的时候，会对 "|" 进行特别处理
    :param refresh: 是否刷新。如果为 True，则会执行网络请求以查询；如果为 False，则直接从 `id_to_dirnode` 中获取
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 文件或目录的 id
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    def gen_step():
        nonlocal ensure_file, cid, id_to_dirnode
        payload = cast(dict, share_extract_payload(share_code))
        if receive_code:
            payload["receive_code"] = receive_code
        if id_to_dirnode is None:
            id_to_dirnode = ID_TO_DIRNODE_CACHE[payload["share_code"]]
        request_kwargs.update(payload)
        error = FileNotFoundError(errno.ENOENT, f"no such path: {path!r}")
        if isinstance(path, str):
            if path.startswith("/"):
                cid = 0
            if path in (".", "..", "/"):
                if ensure_file:
                    raise error
                return cid
            elif path.startswith("根目录 > "):
                cid = 0
                patht = path.split(" > ")[1:]
            elif is_posixpath:
                if ensure_file is None and path.endswith("/"):
                    ensure_file = False
                patht = [p for p in path.split("/") if p]
            else:
                if ensure_file is None and path_is_dir_form(path):
                    ensure_file = False
                patht, _ = splits(path.lstrip("/"))
        else:
            if path and not path[0]:
                cid = 0
                patht = list(path[1:])
            else:
                patht = [p for p in path if p]
            if not patht:
                return cid
        if not patht:
            if ensure_file:
                raise error
            return cid
        i = 0
        if not refresh and id_to_dirnode and id_to_dirnode is not ...:
            if i := len(patht) - bool(ensure_file):
                obj = "|" if is_posixpath else "/"
                for i in range(i):
                    if obj in patht[i]:
                        break
                else:
                    i += 1
            if i:
                for i in range(i):
                    needle = (patht[i], cid)
                    for fid, key in id_to_dirnode.items():
                        if needle == key:
                            cid = fid
                            break
                    else:
                        break
                else:
                    i += 1
        if i == len(patht):
            return cid
        for name in patht[i:-1]:
            if is_posixpath:
                name = name.replace("/", "|")
            with with_iter_next(share_iterdir(
                client, 
                cid=cid, 
                id_to_dirnode=id_to_dirnode, 
                async_=async_, 
                **request_kwargs, 
            )) as get_next:
                found = False
                while not found:
                    attr = yield get_next()
                    found = attr["is_dir"] and (attr["name"].replace("/", "|") if is_posixpath else attr["name"]) == name
                    cid = attr["id"]
            if not found:
                raise error
        name = patht[-1]
        if is_posixpath:
            name = name.replace("/", "|")
        with with_iter_next(share_iterdir(
            client, 
            cid=cid, 
            id_to_dirnode=id_to_dirnode, 
            async_=async_, 
            **request_kwargs, 
        )) as get_next:
            while True:
                attr = yield get_next()
                if (attr["name"].replace("/", "|") if is_posixpath else attr["name"]) == name:
                    if ensure_file is None or ensure_file ^ attr["is_dir"]:
                        return P115ID(attr["id"], attr, about="path")
        raise error
    return run_gen_step(gen_step, async_)


@overload
def share_get_id_to_name(
    client: str | PathLike | P115Client, 
    name: str, 
    share_code: str, 
    receive_code: str = "", 
    size: int = -1, 
    cid: int | str = 0, 
    ensure_file: None | bool = None, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> P115ID:
    ...
@overload
def share_get_id_to_name(
    client: str | PathLike | P115Client, 
    name: str, 
    share_code: str, 
    receive_code: str = "", 
    size: int = -1, 
    cid: int | str = 0, 
    ensure_file: None | bool = None, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, P115ID]:
    ...
def share_get_id_to_name(
    client: str | PathLike | P115Client, 
    name: str, 
    share_code: str, 
    receive_code: str = "", 
    size: int = -1, 
    cid: int | str = 0, 
    ensure_file: None | bool = None, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> P115ID | Coroutine[Any, Any, P115ID]:
    """对分享链接，获取 sha1 对应的文件的 id

    .. caution::
        这个函数并不会检查输入的 ``name`` 是否合法

    :param client: 115 客户端或 cookies
    :param name: 文件名
    :param share_code: 分享码或链接
    :param receive_code: 接收码
    :param size: 文件大小
    :param cid: 顶层目录 id
    :param ensure_file: 是否确保为文件

        - True:  确定是文件
        - False: 确定是目录
        - None:  不确定

    :param app: 使用指定 app（设备）的接口
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 文件或目录的 id
    """
    assert share_code and name
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    def gen_step():
        search = client.share_search
        payload = cast(dict, share_extract_payload(share_code))
        if receive_code:
            payload["receive_code"] = receive_code
        payload.update({
            "cid": cid, 
            "limit": 10_000, 
            "search_value": name, 
        })
        if ensure_file:
            payload["fc"] = 0
            suffix = name.rpartition(".")[-1]
            if suffix.isalnum():
                payload["suffix"] = suffix
        elif ensure_file is False:
            payload["fc"] = 1
        resp: dict = yield search(payload, async_=async_, **request_kwargs)
        if ensure_file and get_first(resp, "errno", "errNo", default=0) == 20021:
            payload.pop("suffix")
            resp = yield search(payload, async_=async_, **request_kwargs)
        check_response(resp)
        for attr in map(normalize_attr, resp["data"]["list"]):
            if attr["name"] == name and (
                not ensure_file or 
                size < 0 or 
                attr["size"] == size
            ):
                return P115ID(attr["id"], attr, about="name", name=name)
        throw(
            errno.ENOENT, 
            {"state": False, "share_code": share_code, "name": name, "size": size, "cid": cid, "error": "not found"}, 
        )
    return run_gen_step(gen_step, async_)


@overload
def get_file_count(
    client: str | PathLike | P115Client, 
    cid: int | str = 0, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    use_fs_files: bool = False, 
    *, 
    async_: Literal[False] = False, 
    **request_kwargs, 
) -> int:
    ...
@overload
def get_file_count(
    client: str | PathLike | P115Client, 
    cid: int | str = 0, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    use_fs_files: bool = False, 
    *, 
    async_: Literal[True], 
    **request_kwargs, 
) -> Coroutine[Any, Any, int]:
    ...
def get_file_count(
    client: str | PathLike | P115Client, 
    cid: int | str = 0, 
    id_to_dirnode: None | EllipsisType | MutableMapping[int, tuple[str, int]] = None, 
    app: str = "web", 
    use_fs_files: bool = False, 
    *, 
    async_: Literal[False, True] = False, 
    **request_kwargs, 
) -> int | Coroutine[Any, Any, int]:
    """获取文件总数

    .. caution::
        如果 ``use_fs_files = True``，但 ``cid`` 不存在、已经被删除或者是文件，那么相当于 ``cid = 0``，这会导致导致长久的等待

    :param client: 115 客户端或 cookies
    :param cid: 目录 id 或 pickcode
    :param id_to_dirnode: 字典，保存 id 到对应文件的 ``(name, parent_id)`` 元组的字典
    :param app: 使用指定 app（设备）的接口
    :param use_fs_files: 使用 `client.fs_files`，否则使用 `client.fs_category_get`
    :param async_: 是否异步
    :param request_kwargs: 其它请求参数

    :return: 目录内的文件总数（不包括目录）
    """
    if isinstance(client, (str, PathLike)):
        client = P115Client(client, check_for_relogin=True)
    def gen_step(cid: int = to_id(cid), /):
        if not cid:
            resp = yield client.fs_space_summury(async_=async_, **request_kwargs)
            check_response(resp)
            return sum(v["count"] for k, v in resp["type_summury"].items() if k.isupper())
        elif use_fs_files:
            with with_iter_next(iter_list(
                client, 
                cid, 
                page_size=1, 
                payload={"hide_data": 1, "show_dir": 0}, 
                normalize_attr=None, 
                id_to_dirnode=id_to_dirnode, 
                app=app, 
                async_=async_, 
                **request_kwargs, 
            )) as get_next:
                resp = yield get_next()
            return int(resp["count"])
        else:
            resp = yield get_info(
                client, 
                cid, 
                id_to_dirnode=id_to_dirnode, 
                app=app, 
                async_=async_, 
                **request_kwargs, 
            )
            if resp["sha1"]:
                resp["cid"] = cid
                raise NotADirectoryError(errno.ENOTDIR, resp)
            return int(resp["count"])
    return run_gen_step(gen_step, async_)

