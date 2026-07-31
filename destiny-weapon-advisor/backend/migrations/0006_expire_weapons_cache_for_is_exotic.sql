-- weapon_to_dict gained an isExotic field, but weapons_cache holds DTO blobs
-- written before it existed. /api/outfits reads that cache, and a weapon dict
-- without isExotic makes every weapon look non-exotic — so the one-exotic-weapon
-- rule silently stops applying and an outfit the player cannot equip is offered
-- as if it were valid. Drop the stale blobs so they are rebuilt on next load.
DELETE FROM user_cache WHERE cache_key = 'weapons_cache';
