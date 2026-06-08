ALTER TABLE classes ADD COLUMN IF NOT EXISTS org_type VARCHAR NOT NULL DEFAULT 'university';
UPDATE classes c SET org_type = (SELECT org_type FROM users WHERE id = c.created_by) WHERE org_type = 'university';
