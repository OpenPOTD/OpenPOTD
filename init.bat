
@echo off

mkdir config
echo "confgured"
COPY  default_config.yml config\config.yml
echo "copied"
copy /b config\token.txt +,,
echo "copied 2.0"
mkdir data
echo "made directory"
sqlite3 data\data.db

