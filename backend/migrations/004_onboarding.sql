ALTER TABLE users ADD COLUMN onboarding_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE users ADD COLUMN onboarding_genres TEXT NOT NULL DEFAULT '[]';
