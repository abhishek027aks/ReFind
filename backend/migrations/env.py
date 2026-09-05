from logging.config import fileConfig
import os
from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
configured_url = os.environ.get("REFIND_DATABASE_URL") or config.get_main_option("sqlalchemy.url")
config.set_main_option("sqlalchemy.url", configured_url.replace("%", "%%"))

def run_migrations_offline():
    context.configure(url=configured_url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        {"sqlalchemy.url": configured_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
