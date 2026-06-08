ALTER TABLE ai_usage_logs ADD COLUMN IF NOT EXISTS org_type VARCHAR NOT NULL DEFAULT 'university';

UPDATE ai_usage_logs l
SET org_type = (SELECT org_type FROM users WHERE id = l.user_id)
WHERE l.user_id IS NOT NULL;
