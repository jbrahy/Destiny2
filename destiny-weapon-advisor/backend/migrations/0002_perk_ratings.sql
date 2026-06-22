-- Fix user_perk_ratings: replace hash-based schema with name-based schema
-- matching the actual PerkRatings model (perk_name, weapon_type, rating, reason, tags, notes)

DROP TABLE IF EXISTS user_perk_ratings;
CREATE TABLE user_perk_ratings (
  user_id BIGINT(20) UNSIGNED NOT NULL,
  perk_name VARCHAR(190) NOT NULL,
  weapon_type VARCHAR(64) NOT NULL DEFAULT '',
  rating CHAR(1) NOT NULL,
  reason TEXT,
  tags VARCHAR(255),
  notes TEXT,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, perk_name, weapon_type),
  CONSTRAINT fk_user_perk_ratings_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
