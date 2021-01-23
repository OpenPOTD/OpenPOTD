CREATE TABLE IF NOT EXISTS "images" (
	"id"	INTEGER NOT NULL PRIMARY KEY,
	"potd_id"	INTEGER,
	"image"	BLOB,
	FOREIGN KEY("potd_id") REFERENCES "problems"("id")
);
CREATE TABLE IF NOT EXISTS "attempts" (
	"id"	INTEGER NOT NULL PRIMARY KEY,
	"user_id"	INTEGER NOT NULL,
	"potd_id"	INTEGER NOT NULL,
	"official"	BOOLEAN,
	"submission"	INTEGER,
	"submit_time"	DATETIME,
	FOREIGN KEY("user_id") REFERENCES "users"("discord_id"),
	FOREIGN KEY("potd_id") REFERENCES "problems"("id")
);
CREATE TABLE IF NOT EXISTS "ratings" (
	"id"	INTEGER NOT NULL PRIMARY KEY,
	"userid"	INTEGER,
	"problemid"	INTEGER,
	"rating"	INTEGER,
	FOREIGN KEY("userid") REFERENCES "users"("discord_id"),
	FOREIGN KEY("problemid") REFERENCES "problems"("id")
);
CREATE TABLE IF NOT EXISTS "seasons" (
	"id"	INTEGER NOT NULL PRIMARY KEY,
	"running"	BOOLEAN NOT NULL,
	"latest_potd"	INTEGER,
	"name"	TEXT,
	"bronze_cutoff" INTEGER,
	"silver_cutoff" INTEGER,
	"gold_cutoff"   INTEGER,
	"public"        BOOLEAN,
	FOREIGN KEY("latest_potd") REFERENCES "problems"("id")
);
CREATE TABLE IF NOT EXISTS "solves" (
	"id"	INTEGER NOT NULL PRIMARY KEY,
	"user"	INTEGER,
	"problem_id"	INTEGER,
	"num_attempts"	INTEGER,
	"official"	BOOLEAN,
	FOREIGN KEY("user") REFERENCES "users"("discord_id"),
	FOREIGN KEY("problem_id") REFERENCES "problems"("id")
);
CREATE TABLE IF NOT EXISTS "rankings" (
	"id"	INTEGER NOT NULL PRIMARY KEY,
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
	"receiving_medal_roles"   BOOLEAN DEFAULT TRUE,
	PRIMARY KEY("discord_id")
);
CREATE TABLE IF NOT EXISTS "problems" (
	"id"	INTEGER NOT NULL PRIMARY KEY,
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
	"difficulty_rating" REAL,
	"coolness_rating"   REAL,
	FOREIGN KEY("season") REFERENCES "seasons"("id")
);
CREATE TABLE IF NOT EXISTS "config" (
	"server_id"	INTEGER,
	"potd_channel"	INTEGER,
	"ping_role_id"	INTEGER,
	"solved_role_id"	INTEGER,
	"otd_prefix"	TEXT,
	"command_prefix"	TEXT,
	"bronze_role_id"    INTEGER,
	"silver_role_id"    INTEGER,
	"gold_role_id"  INTEGER,
	PRIMARY KEY("server_id")
);
CREATE TABLE IF NOT EXISTS "stats_messages" (
	"id"	INTEGER,
	"potd_id"	INTEGER,
	"server_id"     INTEGER,
	"channel_id"    INTEGER,
	"message_id"	INTEGER,
	FOREIGN KEY("potd_id") REFERENCES "problems"("id"),
	PRIMARY KEY("id")
);
CREATE TABLE IF NOT EXISTS "rating_choices" (
	"id"	INTEGER NOT NULL,
	"problem_1_id"	INTEGER NOT NULL,
	"problem_2_id"	INTEGER NOT NULL,
	"choice"	INTEGER,
	"type"	TEXT,
	PRIMARY KEY("id"),
	FOREIGN KEY("problem_2_id") REFERENCES "problems"("id"),
	FOREIGN KEY("problem_1_id") REFERENCES "problems"("id")
)