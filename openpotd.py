import logging
import threading
import time
import traceback
from datetime import date, datetime

import discord
import schedule
from discord import app_commands
from discord.ext import commands
from ruamel.yaml import YAML

import sqlite3

yaml = YAML(typ='safe')
cfgfile = open("config/config.yml")
config = yaml.load(cfgfile)


def adapt_date(val: date):
    return val.isoformat()


def adapt_datetime(val: datetime):
    return val.isoformat(sep=' ')


# The default sqlite3 adapters were deprecated in Python 3.12; register our own
# producing the exact same formats the database already stores.
sqlite3.register_adapter(date, adapt_date)
sqlite3.register_adapter(datetime, adapt_datetime)


class OpenPOTD(commands.Bot):
    def __init__(self):
        # No privileged intents are needed: commands are slash commands (their
        # payloads arrive through interactions) and answers are submitted in
        # DMs, which always carry their content. command_prefix is only a
        # required argument of commands.Bot; it never applies any more.
        intents = discord.Intents.default()

        allowed_mentions = discord.AllowedMentions.all()
        allowed_mentions.everyone = False

        super().__init__(commands.when_mentioned, intents=intents, allowed_mentions=allowed_mentions)
        self.config = config
        self.db = sqlite3.connect('data/data.db')
        logging.basicConfig(level=logging.INFO, format='[%(name)s %(levelname)s] %(message)s')
        self.logger = logging.getLogger('bot')
        try:
            with open(f'config/{config["blacklist"]}', 'r') as blacklist:
                self.blacklist = list(map(
                    int, filter(lambda x: x.strip(), blacklist.readlines())
                ))
        except IOError:
            self.blacklist = []

        # Set refreshing status
        self.posting_problem = False

        self.tree.on_error = self.on_app_command_error

    async def on_ready(self):
        self.logger.info('Connected to Discord')
        self.logger.info('Guilds  : {}'.format(len(self.guilds)))
        self.logger.info('Channels: {}'.format(len(list(self.get_all_channels()))))
        await self.set_presence(self.config['presence'])

        for cog in self.config['cogs']:
            try:
                await self.load_extension(cog)
            except Exception:
                self.logger.exception('Failed to load cog {}.'.format(cog))
            else:
                self.logger.info('Loaded cog {}.'.format(cog))

        await self.tree.sync()

        self.logger.info(f'Schedule: {schedule.jobs}')

    async def on_message(self, message):
        # Prefix commands were removed; the Interface cog listens for answer
        # submissions in DMs on its own, so the bot processes no messages.
        pass

    async def set_presence(self, text):
        game = discord.Game(name=text)
        await self.change_presence(activity=game)

    async def respond(self, interaction: discord.Interaction, content: str):
        """Send an ephemeral error message, coping with commands that had already
        deferred or replied before failing. """
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content, ephemeral=True)
            else:
                await interaction.response.send_message(content, ephemeral=True)
        except discord.HTTPException:
            pass

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandInvokeError):
            # all exceptions are wrapped in CommandInvokeError if they are not a subclass of AppCommandError
            # you can access the original exception with .original
            error: app_commands.CommandInvokeError
            if isinstance(error.original, discord.Forbidden):
                # permissions error
                await self.respond(interaction, 'Permissions error: `{}`'.format(error.original))
                return

            elif isinstance(error.original, discord.HTTPException):
                await self.respond(interaction, 'Sorry, I can\'t send that.')
                return

            # Print to log then notify developers
            try:
                lines = traceback.format_exception(type(error.original),
                                                   error.original,
                                                   error.original.__traceback__)
            except RecursionError:
                raise error

            self.logger.error(''.join(lines))

            return

        if isinstance(error, app_commands.CheckFailure):
            # A bare CheckFailure carries a developer-facing message from discord.py
            # ('The check functions for command ... failed.'), so reply with our own.
            # Subclasses (e.g. NoPrivateMessage) carry their own user-facing text.
            if type(error) is app_commands.CheckFailure:
                await self.respond(interaction, "You are not authorised to use this command. ")
            else:
                await self.respond(interaction, str(error))

        elif isinstance(error, app_commands.CommandOnCooldown):
            error: app_commands.CommandOnCooldown
            await self.respond(interaction, f'You\'re going too fast! Try again in {error.retry_after:.2f} seconds.')

        elif isinstance(error, app_commands.TransformerError):
            await self.respond(interaction, 'Huh? {}'.format(error))

        elif isinstance(error, app_commands.AppCommandError):
            # Errors raised deliberately by our own code (e.g. POTDTransformer)
            # propagate as-is and carry a user-facing message.
            await self.respond(interaction, str(error))
        else:
            info = traceback.format_exception(type(error), error, error.__traceback__, chain=False)
            self.logger.error('Unhandled command exception - {}'.format(''.join(info)))

    async def started_posting(self):
        await self.set_presence('Posting new problem')
        self.posting_problem = True

    async def finished_posting(self):
        await self.set_presence(self.config['presence'])
        self.posting_problem = False


def executor():
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    with open(f'config/{config["token"]}') as tokfile:
        token = tokfile.readline().rstrip('\n')

    x = threading.Thread(target=executor, args=(), daemon=True)
    x.start()
    OpenPOTD().run(token)
