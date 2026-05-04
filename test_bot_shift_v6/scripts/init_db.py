import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import asyncio

from bot.database import acquire, close_pool, init_pool
from web.auth import hash_password
from web.config import web_settings

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        tg_id BIGINT NOT NULL UNIQUE,
        username VARCHAR(255) NULL,
        full_name VARCHAR(255) NULL,
        phone VARCHAR(32) NULL,
        position VARCHAR(255) NULL,
        role ENUM('employee','manager','admin') NOT NULL DEFAULT 'employee',
        hourly_rate DECIMAL(10,2) NOT NULL DEFAULT 0,
        is_active TINYINT(1) NOT NULL DEFAULT 1,
        late_excuse_token TINYINT(1) NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS user_schedules (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        weekdays_json VARCHAR(64) NOT NULL,
        start_time CHAR(5) NOT NULL,
        end_time CHAR(5) NOT NULL,
        is_active TINYINT(1) NOT NULL DEFAULT 1,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        CONSTRAINT fk_user_schedules_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS payroll_periods (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        start_at DATETIME NOT NULL,
        end_at DATETIME NULL,
        is_closed TINYINT(1) NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        CONSTRAINT fk_payroll_periods_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        INDEX idx_payroll_user_open (user_id, is_closed)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS shifts (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        payroll_period_id BIGINT NOT NULL,
        opened_at DATETIME NOT NULL,
        closed_at DATETIME NULL,
        duration_seconds INT NOT NULL DEFAULT 0,
        late_seconds INT NOT NULL DEFAULT 0,
        is_scheduled TINYINT(1) NOT NULL DEFAULT 0,

        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,

        CONSTRAINT fk_shifts_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        CONSTRAINT fk_shifts_period FOREIGN KEY (payroll_period_id) REFERENCES payroll_periods(id) ON DELETE CASCADE,
        INDEX idx_shifts_user_open (user_id, closed_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS reports (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        description TEXT NOT NULL,
        photo_file_id VARCHAR(255) NOT NULL,
        photo_public_url VARCHAR(500) NULL,
        photo_local_path VARCHAR(500) NULL,
        created_at DATETIME NOT NULL,
        CONSTRAINT fk_reports_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        INDEX idx_reports_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS fines (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        payroll_period_id BIGINT NOT NULL,
        amount DECIMAL(10,2) NOT NULL,
        reason TEXT NOT NULL,
        created_at DATETIME NOT NULL,
        created_by BIGINT NOT NULL,
        CONSTRAINT fk_fines_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        CONSTRAINT fk_fines_period FOREIGN KEY (payroll_period_id) REFERENCES payroll_periods(id) ON DELETE CASCADE,
        INDEX idx_fines_user_period (user_id, payroll_period_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS bot_settings (
        `key` VARCHAR(100) PRIMARY KEY,
        `value` VARCHAR(255) NOT NULL,
        updated_at DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS schedule_notification_logs (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        reminder_type VARCHAR(50) NOT NULL,
        reminder_date DATE NOT NULL,
        created_at DATETIME NOT NULL,
        CONSTRAINT fk_schedule_notification_logs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE KEY uq_schedule_notification_log (user_id, reminder_type, reminder_date),
        INDEX idx_schedule_notification_logs_date (reminder_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS catalogs (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        title VARCHAR(255) NOT NULL,
        tags_text VARCHAR(500) NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        CONSTRAINT fk_catalogs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        INDEX idx_catalogs_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS catalog_photos (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        catalog_id BIGINT NOT NULL,
        photo_file_id VARCHAR(255) NOT NULL,
        photo_public_url VARCHAR(500) NULL,
        photo_local_path VARCHAR(500) NULL,
        created_at DATETIME NOT NULL,
        CONSTRAINT fk_catalog_photos_catalog FOREIGN KEY (catalog_id) REFERENCES catalogs(id) ON DELETE CASCADE,
        INDEX idx_catalog_photos_catalog (catalog_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS admin_users (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        role ENUM('superadmin','manager') NOT NULL DEFAULT 'manager',
        is_active TINYINT(1) NOT NULL DEFAULT 1,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
]

DEFAULTS = [
    (
        "INSERT INTO bot_settings (`key`, `value`, updated_at) VALUES (%s, %s, NOW()) "
        "ON DUPLICATE KEY UPDATE `value`=VALUES(`value`), updated_at=VALUES(updated_at)",
        ('latest_reports_days', '10'),
    ),
    (
        "INSERT INTO bot_settings (`key`, `value`, updated_at) VALUES (%s, %s, NOW()) "
        "ON DUPLICATE KEY UPDATE `value`=VALUES(`value`), updated_at=VALUES(updated_at)",
        ('new_report_recipient_ids', ''),
    ),
    (
        "INSERT INTO bot_settings (`key`, `value`, updated_at) VALUES (%s, %s, NOW()) "
        "ON DUPLICATE KEY UPDATE `value`=VALUES(`value`), updated_at=VALUES(updated_at)",
        ('shift_event_recipient_ids', ''),
    )
]

ALTERS = [
    "ALTER TABLE reports ADD COLUMN photo_public_url VARCHAR(500) NULL AFTER photo_file_id",
    "ALTER TABLE reports ADD COLUMN photo_local_path VARCHAR(500) NULL AFTER photo_public_url",
    
    "ALTER TABLE users ADD COLUMN late_excuse_token TINYINT(1) NOT NULL DEFAULT 0 AFTER is_active",
    "ALTER TABLE users MODIFY COLUMN role ENUM('employee','manager','admin') NOT NULL DEFAULT 'employee'",
    "ALTER TABLE catalog_photos ADD COLUMN photo_public_url VARCHAR(500) NULL AFTER photo_file_id",
    "ALTER TABLE catalog_photos ADD COLUMN photo_local_path VARCHAR(500) NULL AFTER photo_public_url",
]



async def main() -> None:
    await init_pool()
    async with acquire() as conn:
        async with conn.cursor() as cur:
            for query in SCHEMA:
                await cur.execute(query)
            for query, args in DEFAULTS:
                await cur.execute(query, args)
            for query in ALTERS:
                try:
                    await cur.execute(query)
                except Exception:
                    pass
            await cur.execute('SELECT id FROM admin_users WHERE username=%s LIMIT 1', (web_settings.web_admin_username,))
            existing = await cur.fetchone()
            if not existing:
                await cur.execute(
                    'INSERT INTO admin_users (username, password_hash, role, is_active, created_at, updated_at) VALUES (%s, %s, %s, 1, NOW(), NOW())',
                    (web_settings.web_admin_username, hash_password(web_settings.web_admin_password), web_settings.web_admin_role),
                )
    await close_pool()
    print('Database initialized successfully')


if __name__ == '__main__':
    asyncio.run(main())
