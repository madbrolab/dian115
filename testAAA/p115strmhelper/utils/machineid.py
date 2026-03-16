__all__ = ["MachineID"]


import uuid
import hashlib
from pathlib import Path
from typing import Optional
import socket
import platform

from orjson import loads, dumps, JSONDecodeError, OPT_INDENT_2


class MachineID:
    """
    Machine ID 管理类
    生成和读取 64 字符的唯一机器标识符
    """

    @staticmethod
    def has_machine_id(config_path: Optional[Path] = None) -> bool:
        """
        检查是否已经生成过 machine id

        :param config_path: 存储 machine id 的文件路径
        :return: 如果存在返回 True，否则 False
        """
        path = config_path
        return path.exists()

    @staticmethod
    def generate_machine_id(config_path: Optional[Path] = None) -> str:
        """
        生成一个新的 64 字符 machine id 并保存到文件。

        :param config_path: 存储 machine id 的文件路径。如果为 None，则使用默认路径。
        :return: 生成的 machine id (64 字符十六进制字符串)。
        :raises FileExistsError: 如果 machine id 文件已存在。
        :raises RuntimeError: 如果无法写入文件或创建目录。
        """
        path = config_path

        if MachineID.has_machine_id(path):
            raise FileExistsError(f"Machine ID file already exists at {path}")

        unique_data = (
            str(uuid.uuid1())
            + str(uuid.uuid4())
            + str(uuid.getnode())
            + socket.gethostname()
            + platform.platform()
        )

        hash_obj = hashlib.sha256(unique_data.encode("utf-8"))
        machine_id = hash_obj.hexdigest()

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            with path.open("wb") as f:
                f.write(dumps({"machine_id": machine_id}, option=OPT_INDENT_2))
        except FileExistsError as e:
            raise FileExistsError(
                f"Machine ID file already exists at {path}, likely due to a race condition."
            ) from e
        except OSError as e:
            raise RuntimeError(
                f"Failed to create directory or write machine ID to {path}: {e}"
            ) from e

        return machine_id

    @staticmethod
    def read_machine_id(config_path: Optional[Path] = None) -> str:
        """
        从文件中读取 machine id。

        :param config_path: 存储 machine id 的文件路径。如果为 None，则使用默认路径。
        :return: 读取到的 machine id (64 字符十六进制字符串)。
        :raises FileNotFoundError: 如果文件不存在。
        :raises ValueError: 如果文件内容无效或格式不正确。
        """
        path = config_path

        if not MachineID.has_machine_id(path):
            raise FileNotFoundError(f"Machine ID file not found at {path}")

        try:
            content = path.read_text(encoding="utf-8")
            data = loads(content)
            machine_id = data.get("machine_id")

            if not isinstance(machine_id, str) or len(machine_id) != 64:
                config_path.unlink(missing_ok=True)
                return MachineID.generate_machine_id(path)

            return machine_id
        except JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON format in machine ID file {path}: {e}"
            ) from e
        except (OSError, Exception) as e:
            raise IOError(f"Failed to read machine ID from {path}: {e}") from e

    @staticmethod
    def get_or_generate_machine_id(config_path: Optional[Path] = None) -> str:
        """
        获取现有的 machine id，如果不存在则生成一个新的。

        :param config_path: 存储 machine id 的文件路径。
        :return: machine id。
        """
        path = config_path
        if MachineID.has_machine_id(path):
            return MachineID.read_machine_id(path)

        return MachineID.generate_machine_id(path)
