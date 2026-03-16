import json
import importlib

from alembic.config import Config as AlembicConfig
from alembic.command import revision as alembic_revision

from app.core.config import settings

plugin_id = None
while not plugin_id:
    plugin_id = input("请输入插件ID(大小写不敏感，后续转换为小写使用)：").strip()
    # 检查这个id对应的插件目录是否存在
    if not (settings.ROOT_PATH / "app" / "plugins" / plugin_id.lower()).exists():
        print(f"插件ID [{plugin_id}] 不存在，请重新输入")
        plugin_id = None
    else:
        check = input(f"插件ID [{plugin_id}] 确认(Y/n): ").strip().lower()
        if not check == "y":
            plugin_id = None
plugin_id = plugin_id.lower()

# 读取 migration_meta.json
if not (
    config_file_path := (
        settings.ROOT_PATH / "app" / "plugins" / plugin_id / "migration_meta.json"
    )
).exists():
    print(f"插件ID [{plugin_id}] 下未找到 migration_meta.json 文件，无法继续")
    exit(1)

db_file_name = None
version = None
script_location = "database"
version_location = ""
models = None
is_new_branch = False
config_data = {}

if config_file_path.is_file():
    try:
        with open(config_file_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        models = config_data.get("models", "")
        script_location = config_data.get("script_location", script_location)
        version_location = config_data.get("version_location", version_location)
        version = config_data.get("version", "1.0.0")
        db_file_name = config_data.get("db_file_name", None)
    except Exception as err:
        print(f"读取 migration.json 出错: {err}")

if not models:
    print(f"插件ID [{plugin_id}] 下 migration_meta.json 未配置 models 的路径，无法继续")
    exit(1)
else:
    models_fs_path = models.replace(".", "/")

# 交互式输入版本号
new_version = input(f"请输入版本号 (当前版本: {version})：") or version

# 构造数据库文件路径，如果 db_file_name 为空则使用默认的 user.db
if not db_file_name:
    db_location = settings.CONFIG_PATH / "user.db"
else:
    db_location = settings.PLUGIN_DATA_PATH / plugin_id / db_file_name

# 构造脚本路径，env.py 和 mako 需要在这个路径下
script_fs_path = script_location.replace(".", "/")
script_location_path = (
    settings.ROOT_PATH / "app" / "plugins" / plugin_id / script_fs_path
)

# versions 存放目录
version_fs_path = version_location.replace(".", "/")
version_location_path = (
    settings.ROOT_PATH / "app" / "plugins" / plugin_id / version_fs_path
)
# 如果结尾不是 versions，则补上
if version_location_path and not str(version_location_path).endswith("versions"):
    version_location_path = version_location_path / "versions"

# 检查版本目录是否存在，且包含至少一个 .py 文件
if (
    not version_location_path.exists()
    or not version_location_path.is_dir()
    or not any(version_location_path.glob("*.py"))
):
    print(
        f"脚本路径 {version_location_path} 不存在，视为首次创建，准备分配 {plugin_id} 分支"
    )
    is_new_branch = True

# 配置 Alembic
alembic_cfg = AlembicConfig()
alembic_cfg.set_main_option("script_location", str(script_location_path))
alembic_cfg.set_main_option("version_locations", str(version_location_path))
alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_location}")

# 设置文件名格式
filename_prefix = f"{plugin_id}-v{new_version}"
alembic_cfg.set_main_option("file_template", f"{filename_prefix}-%%(rev)s")

# 传递自定义变量
alembic_cfg.attributes["plugin_id"] = plugin_id
alembic_cfg.attributes["version"] = new_version


# 构造正确的文件搜索路径
search_path = settings.ROOT_PATH.joinpath("app", "plugins", plugin_id, models_fs_path)


for module_file in search_path.glob("*.py"):
    # 忽略 __init__.py 文件
    if module_file.stem == "__init__":
        continue

    # 构造Python模块导入路径
    module_to_import = f"app.plugins.{plugin_id}.{models}.{module_file.stem}"
    print(f"\n动态导入模型文件: {module_to_import}")

    # 执行导入
    try:
        importlib.import_module(module_to_import)
    except ImportError as e:
        print(f"\n导入 {module_to_import} 失败: {e}")

new_revision_script = alembic_revision(
    config=alembic_cfg,
    message=new_version,
    autogenerate=True,
    branch_label=plugin_id if is_new_branch else None,
)

new_revision_id = None
if new_revision_script:
    # autogenerate 可能返回列表，也可能返回单个对象
    script_object = (
        new_revision_script[0]
        if isinstance(new_revision_script, list)
        else new_revision_script
    )
    if script_object:
        new_revision_id = script_object.revision
        print(f"\n成功生成新的 Revision ID: {new_revision_id}")
else:
    print("\n警告：Alembic 未返回新的 revision 对象，可能因为模型没有变化。")

print("\n迁移脚本生成成功，正在更新 migration_meta.json...")
try:
    # 更新内存中的字典
    config_data["version"] = new_version
    if new_revision_id:
        config_data["revision"] = new_revision_id
    # 以写入模式打开文件并写回
    with open(config_file_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=4)

    print(f"成功将 version 更新为: {new_version}")
    print(f"成功将 revision 更新为: {new_revision_id}")

except Exception as e:
    print(f"错误：更新 migration_meta.json 文件失败: {e}")
