CREATE TABLE IF NOT EXISTS users (
  user_id     INTEGER PRIMARY KEY,
  referrer_id INTEGER,
  joined_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS referrals (
  referrer_id INTEGER,
  referred_id INTEGER,
  PRIMARY KEY (referrer_id, referred_id)
);
