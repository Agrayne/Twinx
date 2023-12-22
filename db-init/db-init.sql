CREATE TABLE IF NOT EXISTS guilds (
    "guildId" BIGINT NOT NULL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS channels (
    "channelId" BIGINT NOT NULL PRIMARY KEY,
    "webhookId" BIGINT NOT NULL,
    "webhookToken" text NOT NULL,
    "guildId" BIGINT NOT NULL REFERENCES guilds ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS twitterUsers (
    "username" TEXT NOT NULL PRIMARY KEY,
    "hash" TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS subs (
    "username" TEXT REFERENCES twitterUsers ON DELETE CASCADE,
    "channelId" BIGINT REFERENCES channels ON DELETE CASCADE,
    CONSTRAINT sub_key PRIMARY KEY("username", "channelId")
);
