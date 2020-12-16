# OpenPOTD

OpenPOTD is an open source POTD manager discord bot
built to grade short answer and multichoice problems.
At the moment OpenPOTD works, but has very few
features. 

## Running OpenPOTD

Register a bot account with Discord and then run the
`init.sh` script (for Linux / Mac) or `init.bat` script
for Windows. This will create the required config and
data files, then put the token provided by Discord
into the `config/token.txt` file.

## Using OpenPOTD

1. Edit the `config/config.yml` file to your liking. 
1. Add a new season with the `%newseason` command. 
1. Add problems with the `%add` command. 
1. Link images to problems with the `%linkimg` command. 
1. The bot should post problems at the specified time 
every day and alert if there is no problem. 
