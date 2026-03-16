from pathlib import Path
from time import sleep
from typing import Any, Generator, List, Optional, Self, Tuple
from sqlite3 import OperationalError as SqlOperationalError, SQLITE_BUSY

from sqlalchemy import (
    create_engine,
    and_,
    inspect,
    event,
    NullPool,
    QueuePool,
    text,
    Engine,
)
from sqlalchemy.orm import (
    declared_attr,
    sessionmaker,
    scoped_session,
    DeclarativeBase,
    Session,
)
from sqlalchemy.exc import OperationalError

from ..core.config import configer
from app.core.config import settings
from app.log import logger


class __DBManager:
    """
    数据库管理器
    """

    # 数据库引擎
    Engine: Optional[Engine] = None
    # 会话工厂
    SessionFactory: Optional[sessionmaker] = None
    # 多线程全局使用的数据库会话
    ScopedSession: Optional[scoped_session] = None

    @staticmethod
    def _setup_sqlite_pragmas(dbapi_connection, _connection_record):
        """
        事件监听器，在每个新连接上执行

        :param dbapi_connection: 底层数据库连接对象
        :param _connection_record: SQLAlchemy 内部用来记录这个连接信息的对象
        """
        cursor = dbapi_connection.cursor()
        try:
            # 根据配置决定日志模式，暂时根据 mp 的模式来确定
            journal_mode = "WAL" if configer.get_config("DB_WAL_ENABLE") else "DELETE"
            cursor.execute(f"PRAGMA journal_mode={journal_mode};")

            # 如果启用 WAL，必须设置一个合理的忙碌超时时间以处理锁竞争
            if configer.get_config("DB_WAL_ENABLE"):
                # 将超时时间（秒）转换为毫秒
                busy_timeout_ms = int(settings.DB_TIMEOUT * 1000)
                cursor.execute(f"PRAGMA busy_timeout = {busy_timeout_ms};")

            # 设置其他性能优化参数
            cursor.execute("PRAGMA synchronous = NORMAL;")
            cursor.execute("PRAGMA cache_size = -100000;")
            cursor.execute("PRAGMA temp_store = MEMORY;")
            # 设置合理的锁定模式，避免独占锁定
            cursor.execute("PRAGMA locking_mode = NORMAL;")
        finally:
            cursor.close()

    def init_database(self, db_path: Path):
        """
        初始化数据库引擎。
        :param db_path: 数据库路径
        """
        # 数据库已经启动
        if self.is_initialized():
            return
        # 套用 mp 的 timeout
        connect_args = {"timeout": settings.DB_TIMEOUT}
        # 在多线程环境中使用 WAL 模式，必须禁用线程检查
        if configer.get_config("DB_WAL_ENABLE"):
            connect_args["check_same_thread"] = False

        # 根据配置选择连接池类型
        pool_class = NullPool if settings.DB_POOL_TYPE == "NullPool" else QueuePool

        # 组装 create_engine 的所有参数
        db_kwargs = {
            "url": f"sqlite:///{db_path}",
            "pool_pre_ping": settings.DB_POOL_PRE_PING,
            "echo": settings.DB_ECHO,
            "pool_recycle": settings.DB_POOL_RECYCLE,
            "connect_args": connect_args,
        }

        # 如果使用 QueuePool，则添加其特定参数
        if pool_class == QueuePool:
            db_kwargs.update(
                {
                    "pool_size": getattr(settings, "DB_SQLITE_POOL_SIZE", 30),
                    "pool_timeout": settings.DB_POOL_TIMEOUT,
                    "max_overflow": getattr(settings, "DB_SQLITE_MAX_OVERFLOW", 50),
                }
            )

        self.Engine = create_engine(**db_kwargs)

        # 绑定事件监听器，确保 PRAGMA 对所有连接生效（多线程连接用的）
        event.listen(
            target=self.Engine, identifier="connect", fn=self._setup_sqlite_pragmas
        )

        # 创建会话工厂和线程安全的 ScopedSession
        self.SessionFactory = sessionmaker(bind=self.Engine)
        self.ScopedSession = scoped_session(self.SessionFactory)

        logger.info("数据库初始化成功")
        with self.Engine.connect() as conn:
            mode = conn.execute(text("PRAGMA journal_mode;")).scalar()
            logger.debug(f"当前日志模式设置为: {mode.upper()}")

    def perform_checkpoint(self, mode: str = "PASSIVE"):
        """
        执行 SQLite 的 checkpoint 操作

        在 WAL 模式下，将数据从 -wal 文件写回主数据库文件；关闭前会被调用一次；可以上定时任务，定期执行写入，防止 wal 文件积增
        :param mode: checkpoint 模式 (PASSIVE, FULL, RESTART, TRUNCATE)
        """
        #
        if not self.Engine or not configer.get_config("DB_WAL_ENABLE"):
            logger.warning("Checkpoint 操作仅在数据库初始化后且启用 WAL 模式时可用")
            return

        valid_modes = {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}
        if mode.upper() not in valid_modes:
            raise ValueError(
                f"无效的 checkpoint 模式 '{mode}'。必须是 {valid_modes} 中的一个"
            )

        try:
            with self.Engine.connect() as conn:
                # 必须在一个事务中执行 checkpoint 才能生效
                with conn.begin():
                    conn.execute(text(f"PRAGMA wal_checkpoint({mode.upper()});"))
                logger.debug(f"WAL checkpoint 操作（模式: {mode.upper()}）已成功执行")
        except Exception as e:
            logger.error(f"执行 WAL checkpoint 操作期间发生错误: {e}", exc_info=True)

    def close_database(self):
        """
        关闭所有数据库连接并清理资源
        """
        # 检查是否需要并可以执行 checkpoint
        if self.Engine and configer.get_config("DB_WAL_ENABLE"):
            logger.info("正在执行数据库关闭前的最终 checkpoint...")
            # 使用 TRUNCATE 模式以获得最干净的关闭状态
            self.perform_checkpoint(mode="TRUNCATE")

        if self.Engine:
            self.Engine.dispose()
        self.Engine = None
        self.SessionFactory = None
        self.ScopedSession = None

    def is_initialized(self) -> bool:
        """
        判断数据库是否初始化并连接、创建会话工厂
        """
        if (
            self.Engine is None
            or self.SessionFactory is None
            or self.ScopedSession is None
        ):
            return False
        return True


def get_db() -> Generator:
    """
    获取数据库会话，用于WEB请求
    :return: Session
    """
    db = None
    try:
        db = ct_db_manager.SessionFactory()
        yield db
    finally:
        if db:
            db.close()


def get_args_db(args: tuple, kwargs: dict) -> Optional[Session]:
    """
    从参数中获取数据库Session对象
    """
    db = None
    if args:
        for arg in args:
            if isinstance(arg, Session):
                db = arg
                break
    if kwargs:
        for _, value in kwargs.items():
            if isinstance(value, Session):
                db = value
                break
    return db


def update_args_db(args: tuple, kwargs: dict, db: Session) -> Tuple[tuple, dict]:
    """
    更新参数中的数据库Session对象，关键字传参时更新db的值，否则更新第1或第2个参数
    """
    if kwargs and "db" in kwargs:
        kwargs["db"] = db
    elif args:
        if args[0] is None:
            args = (db, *args[1:])
        else:
            args = (args[0], db, *args[2:])
    return args, kwargs


def init_database() -> bool:
    """
    初始化数据库操作
    """
    # 自动初始化数据库管理器
    if not ct_db_manager.is_initialized():
        logger.info("数据库管理器未初始化，正在自动初始化...")

        # 延迟导入避免循环导入
        from .init import init_db, migration_db, init_migration_scripts

        # 初始化数据库
        ct_db_manager.init_database(db_path=configer.PLUGIN_DB_PATH)

        # 初始化数据库表
        init_db(engine=ct_db_manager.Engine)

        # 运行迁移脚本
        if init_migration_scripts():
            migration_db(
                db_path=configer.PLUGIN_DB_PATH,
                script_location=configer.PLUGIN_DATABASE_SCRIPT_LOCATION,
                version_locations=configer.PLUGIN_DATABASE_VERSION_LOCATIONS,
            )

    # 检查 ScopedSession 是否可用
    if ct_db_manager.ScopedSession is None:
        logger.error("数据库会话工厂初始化失败")
        raise RuntimeError("数据库会话工厂初始化失败")

    return True


def db_update(func):
    """
    数据库更新类操作装饰器，第一个参数必须是数据库会话或存在db参数
    """

    def wrapper(*args, **kwargs):
        # 是否关闭数据库会话
        _close_db = False
        db = get_args_db(args, kwargs)
        if not db:
            init_database()
            # 如果没有获取到数据库会话，创建一个
            db = ct_db_manager.ScopedSession()
            # 标记需要关闭数据库会话
            _close_db = True
            # 更新参数中的数据库会话
            args, kwargs = update_args_db(args, kwargs, db)

        max_retries = 3
        retry_delay = 0.1
        last_err = None

        try:
            for attempt in range(max_retries):
                try:
                    # 执行函数
                    result = func(*args, **kwargs)
                    # 提交事务
                    db.commit()
                    return result
                except OperationalError as err:
                    # 回滚事务
                    db.rollback()
                    last_err = err
                    if not (
                        isinstance(err.orig, SqlOperationalError)
                        and err.orig.sqlite_errorcode == SQLITE_BUSY
                    ):
                        raise err

                    logger.warning(
                        f"数据库锁定，第 {attempt + 1} 次重试，等待 {retry_delay}s..."
                    )
                    sleep(retry_delay)
                    retry_delay *= 2
            if last_err:
                raise last_err
        except Exception as err:
            if not isinstance(err, OperationalError):
                db.rollback()
            raise err
        finally:
            # 关闭数据库会话
            if _close_db:
                db.close()

    return wrapper


def db_query(func):
    """
    数据库查询操作装饰器，第一个参数必须是数据库会话或存在db参数
    注意：db.query列表数据时，需要转换为list返回
    """

    def wrapper(*args, **kwargs):
        # 是否关闭数据库会话
        _close_db = False
        # 从参数中获取数据库会话
        db = get_args_db(args, kwargs)
        if not db:
            init_database()
            # 如果没有获取到数据库会话，创建一个
            db = ct_db_manager.ScopedSession()
            # 标记需要关闭数据库会话
            _close_db = True
            # 更新参数中的数据库会话
            args, kwargs = update_args_db(args, kwargs, db)
        try:
            # 执行函数
            result = func(*args, **kwargs)
        except Exception as err:
            raise err
        finally:
            # 关闭数据库会话
            if _close_db:
                db.close()
        return result

    return wrapper


class P115StrmHelperBase(DeclarativeBase):
    id: Any
    __name__: str

    @db_update
    def create(self, db: Session):
        db.add(self)

    @classmethod
    @db_query
    def get(cls, db: Session, rid: int) -> Self:
        return db.query(cls).filter(and_(cls.id == rid)).first()

    @db_update
    def update(self, db: Session, payload: dict):
        payload = {k: v for k, v in payload.items() if v is not None}
        for key, value in payload.items():
            setattr(self, key, value)
        if inspect(self).detached:
            db.add(self)

    @classmethod
    @db_update
    def delete(cls, db: Session, rid):
        db.query(cls).filter(and_(cls.id == rid)).delete()

    @classmethod
    @db_update
    def truncate(cls, db: Session):
        db.query(cls).delete()

    @classmethod
    @db_query
    def list(cls, db: Session) -> List[Self]:
        result = db.query(cls).all()
        return list(result)

    def to_dict(self):
        return {c.name: getattr(self, c.name, None) for c in self.__table__.columns}  # noqa

    @declared_attr
    def __tablename__(self) -> str:
        return self.__name__.lower()


class DbOper:
    """
    数据库操作基类
    """

    _db: Session = None

    def __init__(self, db: Session = None):
        self._db = db


# 全局数据库会话
ct_db_manager = __DBManager()
