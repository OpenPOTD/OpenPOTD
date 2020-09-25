
@echo off

mkdir config
COPY  default_config.yml config\config.yml
copy /b config\token.txt +,,
mkdir data
sqlite3 data\data.db

