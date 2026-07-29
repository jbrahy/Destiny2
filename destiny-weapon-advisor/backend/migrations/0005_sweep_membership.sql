-- Key staged sweep rows by membership, not just user_id: without this, an
-- account switch on the same user_id makes undo see the new account's
-- profile, treat every old-account instance id as "already dismantled in
-- game", and clear_sweep_items wipes the records for weapons that are
-- actually still unlocked on the previous account.
--
-- No deployed instance of this feature exists yet (this table only ever
-- holds an in-progress sweep), so drop-and-recreate is safe here.

DROP TABLE IF EXISTS user_sweep_items;
CREATE TABLE user_sweep_items (
    user_id BIGINT(20) UNSIGNED NOT NULL,
    membership_id VARCHAR(32) NOT NULL,
    instance_id VARCHAR(32) NOT NULL,
    was_locked TINYINT(1) NOT NULL DEFAULT 0,
    staged_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, membership_id, instance_id),
    CONSTRAINT fk_user_sweep_items_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
