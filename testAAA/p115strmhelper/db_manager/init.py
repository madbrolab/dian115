from pathlib import Path
from shutil import copy2
from typing import Set

from orjson import loads
from alembic import command
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.log import logger

from ..db_manager import ct_db_manager, P115StrmHelperBase

# 显式载入，确保表单模型已注册
from ..db_manager.models import *  # noqa


def init_db(engine):
    """
    初始化数据库
    """
    if not engine:
        raise SQLAlchemyError("数据库引擎获取失败")
    # 全量建表
    P115StrmHelperBase.metadata.create_all(engine)


def migration_db(db_path, script_location, version_locations: list):
    """
    更新数据库
    """
    # 启动时的更新，调整从 /config/plugins/p115strmhelper/database/versions 中读取持久化的迁移脚本)
    meta_data_path = Path(
        settings.ROOT_PATH
        / "app"
        / "plugins"
        / "p115strmhelper"
        / "migration_meta.json"
    )
    with open(meta_data_path, "rb") as f:
        config_data = loads(f.read())
        revision = config_data.get("revision", "head")
        logger.debug(f"正在将数据库迁移到版本: {revision} ...")

    # 智能迁移到指定版本
    sync_to_revision(
        sqlalchemy_url=f"sqlite:///{db_path}",
        script_location=str(script_location),
        target_revision=revision,
        version_locations=" ".join(version_locations) if version_locations else None,
    )


def init_migration_scripts() -> bool:
    """
    初始化持久化的迁移脚本，将源目录内容完整复制到目标目录。
    """
    # 使用 Path 对象定义路径
    source_path = Path(
        settings.ROOT_PATH
        / "app"
        / "plugins"
        / "p115strmhelper"
        / "database"
        / "versions"
    )
    target_path = Path(
        settings.PLUGIN_DATA_PATH / "p115strmhelper" / "database" / "versions"
    )

    # 确保源目录存在且是一个目录
    if not source_path.is_dir():
        logger.warning(f"迁移脚本源目录不存在或不是一个目录: {source_path}")
        return False

    # 确保目标目录存在，如果不存在则递归创建
    target_path.mkdir(parents=True, exist_ok=True)

    # 遍历源目录中的所有条目
    logger.debug(f"开始同步迁移脚本从 {source_path} 到 {target_path}...")
    files_copied = 0
    try:
        for source_item in source_path.iterdir():
            # 只处理文件，忽略任何可能的子目录（如 __pycache__）
            if source_item.is_file():
                # 构建目标文件的完整路径
                destination_file = target_path / source_item.name

                # 复制文件（会覆盖已存在的文件）
                copy2(source_item, destination_file)
                files_copied += 1
    except IOError as e:
        logger.error(f"在复制文件时发生 I/O 错误: {e}")
        return False
    except Exception as e:
        logger.error(f"发生未知错误: {e}")
        return False

    logger.debug(
        f"数据库迁移脚本 versions 同步完成，共复制/覆盖了 {files_copied} 个文件。"
    )
    return True


def get_ancestors(script: ScriptDirectory, revision_id: str) -> Set[str]:
    """
    获取给定 revision 的所有祖先（历史版本）。
    """
    ancestors = set()
    # 路径上的所有版本都被认为是“祖先”
    for rev in script.walk_revisions(head=revision_id):
        ancestors.add(rev.revision)
    return ancestors


def sync_to_revision(
    script_location: str,
    sqlalchemy_url: str,
    target_revision: str,
    version_locations: str = None,
):
    """
    智能地将数据库同步到指定的目标版本，无需 alembic.ini 文件。
    """
    logger.info(f"--- 开始智能迁移，目标版本: {target_revision} ---")

    # 创建并配置 Alembic Config 对象
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", script_location)
    if version_locations:
        alembic_cfg.set_main_option("version_locations", version_locations)
    alembic_cfg.set_main_option("sqlalchemy.url", sqlalchemy_url)

    try:
        script = ScriptDirectory.from_config(alembic_cfg)
    except Exception as e:
        logger.error(f"加载 Alembic 环境失败: {e}")
        logger.error("请确保 'script_location' 指向的目录包含有效的 'env.py' 文件。")
        return

    # 解析目标版本号
    try:
        resolved_target_rev = script.as_revision_number(target_revision)
        if resolved_target_rev is None and target_revision.lower() == "base":
            resolved_target_rev = "base"
        elif resolved_target_rev is None:
            raise ValueError(f"目标版本 '{target_revision}' 未找到。")
        logger.info(f"解析后的目标版本 ID: {resolved_target_rev}")
    except Exception as e:
        logger.error(f"无法解析目标版本 '{target_revision}': {e}")
        return

    # 获取数据库当前的版本头 (heads)
    with ct_db_manager.Engine.connect() as connection:
        # 必须先 configure()，然后 get_context()
        env_context = EnvironmentContext(alembic_cfg, script)
        env_context.configure(connection=connection)

        migration_context = env_context.get_context()
        current_heads = set(migration_context.get_current_heads())

    if not current_heads:
        logger.info("数据库当前为空（没有版本记录）。将执行升级操作。")
        command.upgrade(alembic_cfg, resolved_target_rev)
        logger.info(f"--- 成功迁移到版本: {resolved_target_rev} ---")
        return

    logger.info(f"数据库当前版本头: {current_heads}")

    if len(current_heads) > 1:
        logger.error("数据库处于多分支状态，无法自动判断。请手动处理。")
        return

    current_rev = current_heads.pop()

    if current_rev == resolved_target_rev:
        logger.info("目标版本与当前数据库版本相同。无需操作。")
        return

    # 判断是升级、降级还是分支切换
    ancestors_of_current = get_ancestors(script, current_rev)
    ancestors_of_target = (
        get_ancestors(script, resolved_target_rev)
        if resolved_target_rev != "base"
        else {"base"}
    )

    if resolved_target_rev in ancestors_of_current:
        logger.info(
            f"目标版本 '{resolved_target_rev}' 是当前版本 '{current_rev}' 的历史版本。将执行降级操作。"
        )
        command.downgrade(alembic_cfg, resolved_target_rev)
    elif current_rev in ancestors_of_target:
        logger.info(
            f"目标版本 '{resolved_target_rev}' 是当前版本 '{current_rev}' 的未来版本。将执行升级操作。"
        )
        command.upgrade(alembic_cfg, resolved_target_rev)
    else:
        logger.error(
            f"当前版本 '{current_rev}' 和目标版本 '{resolved_target_rev}' "
            "位于不同的迁移分支上。无法自动判断路径。"
            "请先降级到共同的祖先版本，然后再升级。"
        )
        return

    logger.info(f"--- 迁移操作成功完成 ---")
