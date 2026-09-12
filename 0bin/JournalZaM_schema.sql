PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    color       TEXT,
    active      INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date      DATE NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    body_html       TEXT NOT NULL,
    body_plain      TEXT NOT NULL DEFAULT '',
    mood            TEXT,
    day_rating      INTEGER CHECK (day_rating BETWEEN 1 AND 10),
    category_id     INTEGER,
    favorite        INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0,1)),
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS entry_tags (
    entry_id    INTEGER NOT NULL,
    tag_id      INTEGER NOT NULL,
    PRIMARY KEY (entry_id, tag_id),
    FOREIGN KEY (entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS people (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS entry_people (
    entry_id    INTEGER NOT NULL,
    person_id   INTEGER NOT NULL,
    PRIMARY KEY (entry_id, person_id),
    FOREIGN KEY (entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE,
    FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entry_images (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id        INTEGER NOT NULL,
    image_key       TEXT NOT NULL UNIQUE,
    file_name       TEXT,
    mime_type       TEXT,
    image_data      BLOB NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key     TEXT PRIMARY KEY,
    setting_value   TEXT
);

CREATE INDEX IF NOT EXISTS idx_entries_date ON journal_entries(entry_date);
CREATE INDEX IF NOT EXISTS idx_entries_mood ON journal_entries(mood);
CREATE INDEX IF NOT EXISTS idx_entries_category ON journal_entries(category_id);
CREATE INDEX IF NOT EXISTS idx_entries_favorite ON journal_entries(favorite);
CREATE INDEX IF NOT EXISTS idx_entry_tags_entry ON entry_tags(entry_id);
CREATE INDEX IF NOT EXISTS idx_entry_people_entry ON entry_people(entry_id);
CREATE INDEX IF NOT EXISTS idx_images_entry ON entry_images(entry_id);

INSERT OR IGNORE INTO categories(name, color) VALUES
    ('Personal', '#6F9488'),
    ('Work', '#6E86B7'),
    ('Travel', '#B68B55'),
    ('Ideas', '#9B7AB8'),
    ('Books & Culture', '#B97878'),
    ('Health & Wellbeing', '#6D9A72');
