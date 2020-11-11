CREATE TABLE IF NOT EXISTS "images" (
	"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	"potd_id"	INTEGER,
	"image"	BLOB,
	FOREIGN KEY("potd_id") REFERENCES "problems"("id")
);
CREATE TABLE IF NOT EXISTS "attempts" (
	"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	"user_id"	INTEGER NOT NULL,
	"potd_id"	INTEGER NOT NULL,
	"official"	BOOLEAN,
	"submission"	INTEGER,
	"submit_time"	DATETIME,
	FOREIGN KEY("user_id") REFERENCES "users"("discord_id"),
	FOREIGN KEY("potd_id") REFERENCES "problems"("id")
);
CREATE TABLE IF NOT EXISTS "ratings" (
	"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	"userid"	INTEGER,
	"problemid"	INTEGER,
	"rating"	INTEGER,
	FOREIGN KEY("userid") REFERENCES "users"("discord_id"),
	FOREIGN KEY("problemid") REFERENCES "problems"("id")
);
CREATE TABLE IF NOT EXISTS "seasons" (
	"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	"running"	BOOLEAN NOT NULL,
	"latest_potd"	INTEGER,
	"name"	TEXT,
	FOREIGN KEY("latest_potd") REFERENCES "problems"("id")
);
CREATE TABLE IF NOT EXISTS "solves" (
	"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	"user"	INTEGER,
	"problem_id"	INTEGER,
	"num_attempts"	INTEGER,
	"official"	BOOLEAN,
	FOREIGN KEY("user") REFERENCES "users"("discord_id"),
	FOREIGN KEY("problem_id") REFERENCES "problems"("id")
);
CREATE TABLE IF NOT EXISTS "rankings" (
	"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	"season_id"	INTEGER,
	"user_id"	INTEGER,
	"rank"	INTEGER,
	"score"	REAL,
	UNIQUE ("season_id", "user_id")
	FOREIGN KEY("user_id") REFERENCES "users"("discord_id"),
	FOREIGN KEY("season_id") REFERENCES "seasons"("id")
);
CREATE TABLE IF NOT EXISTS "users" (
	"discord_id"	INTEGER NOT NULL UNIQUE,
	"nickname"	TEXT,
	"anonymous"	BOOLEAN,
	PRIMARY KEY("discord_id")
);
CREATE TABLE IF NOT EXISTS "problems" (
	"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
	"date"	DATE NOT NULL,
	"season"	INTEGER NOT NULL,
	"statement"	TEXT NOT NULL,
	"difficulty"	INTEGER,
	"weighted_solves"	INTEGER NOT NULL DEFAULT 0,
	"base_points"	INTEGER NOT NULL DEFAULT 0,
	"answer"	INTEGER NOT NULL,
	"public"	BOOLEAN,
	"source"	TEXT,
	"stats_message_id"	INTEGER,
	FOREIGN KEY("season") REFERENCES "seasons"("id")
);
CREATE TABLE IF NOT EXISTS "config" (
	"server_id"	INTEGER,
	"potd_channel"	INTEGER,
	"ping_role_id"	INTEGER,
	"solved_role_id"	INTEGER,
	"otd_prefix"	TEXT,
	"command_prefix"	TEXT,
	PRIMARY KEY("server_id")
);
