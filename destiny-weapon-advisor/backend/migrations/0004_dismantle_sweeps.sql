CREATE TABLE IF NOT EXISTS user_sweep_items (
    user_id BIGINT(20) UNSIGNED NOT NULL,
    instance_id VARCHAR(32) NOT NULL,
    was_locked TINYINT(1) NOT NULL DEFAULT 0,
    staged_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, instance_id),
    CONSTRAINT fk_user_sweep_items_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
