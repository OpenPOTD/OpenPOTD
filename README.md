# OpenPOTD

OpenPOTD is an open source POTD manager discord bot
built to grade short answer and multichoice problems.
OpenPOTD has many features including automatically 
posting problems, grading submissions, being able to
display and check submissions for past problems (and 
mark them as unofficial), set and give medal roles, and 
being able to give people who solved the potd a special
role (typically to let them talk in a private channel). 

## Adding the OpenPOTD bot

The OpenPOTD team maintains an instance of the OpenPOTD
bot which we pick problems for ourselves. For a tutorial
on how to add the bot and configure it, visit 
https://openpotd.github.io/install/. 

## Running OpenPOTD yourself

Register a bot account with Discord and then run the
`init.sh` script (for Linux / Mac) or `init.bat` script
for Windows. This will create the required config and
data files, then put the token provided by Discord
into the `config/token.txt` file.

### Using OpenPOTD

1. Edit the `config/config.yml` file to your liking. 
1. Add a new season with the `%newseason` command. 
1. Add problems with the `%add` command. 
1. Link images to problems with the `%linkimg` command. 
1. The bot should post problems at the specified time 
every day and alert if there is no problem. 
