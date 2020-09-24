#!/bin/bash

# Creating config files
mkdir config
cp default_config.yml config/default_config.yml
touch config/token.txt  # Fill in the provided token yourself

# Creating database
mkdir data
sqlite3 data/data.db < schema.sql
