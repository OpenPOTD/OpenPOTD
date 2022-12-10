import logging
import re
import threading
import time
import traceback

import discord
import schedule
from discord.ext import commands
from ruamel import yaml

import sqlite3

cfgfile = open("config/config.yml")
config = yaml.safe_load(cfgfile)

prefixes = {}


def get_prefix(bot, message: discord.Message):
    if message.guild is None or message.guild.id not in prefixes:
        return config['prefix']
    else:
        return prefixes[message.guild.id]


class OpenPOTD(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True

        allowed_mentions = discord.AllowedMentions.all()
        allowed_mentions.everyone = False

        super().__init__(get_prefix, intents=intents, allowed_mentions=allowed_mentions)
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

        # Populate prefixes
        cursor = self.db.cursor()
        cursor.execute('SELECT server_id, command_prefix FROM config WHERE command_prefix IS NOT NULL')
        global prefixes
        prefixes = {x[0]: x[1] for x in cursor.fetchall()}

        # Set refreshing status
        self.posting_problem = False

    async def on_ready(self):
        self.logger.info('Connected to Discord')
        self.logger.info('Guilds  : {}'.format(len(self.guilds)))
        self.logger.info('Users   : {}'.format(len(set(self.get_all_members()))))
        self.logger.info('Channels: {}'.format(len(list(self.get_all_channels()))))
        await self.set_presence(self.config['presence'])

        for cog in self.config['cogs']:
            try:
                await self.load_extension(cog)
            except Exception:
                self.logger.exception('Failed to load cog {}.'.format(cog))
            else:
                self.logger.info('Loaded cog {}.'.format(cog))

        self.logger.info(f'Schedule: {schedule.jobs}')

    async def on_message(self, message):
        if message.author.bot: return
        if message.author.id in self.blacklist: return
        await self.process_commands(message)

    async def set_presence(self, text):
        game = discord.Game(name=text)
        await self.change_presence(activity=game)

    async def on_command_error(self, ctx: commands.Context, exception: Exception):
        if isinstance(exception, commands.CommandInvokeError):
            # all exceptions are wrapped in CommandInvokeError if they are not a subclass of CommandError
            # you can access the original exception with .original
            exception: commands.CommandInvokeError
            if isinstance(exception.original, discord.Forbidden):
                # permissions error
                try:
                    await ctx.send('Permissions error: `{}`'.format(exception))
                except discord.Forbidden:
                    # we can't send messages in that channel
                    pass
                return

            elif isinstance(exception.original, discord.HTTPException):
                try:
                    await ctx.send('Sorry, I can\'t send that.')
                except discord.Forbidden:
                    pass

                return

            # Print to log then notify developers
            try:
                lines = traceback.format_exception(type(exception),
                                                   exception,
                                                   exception.__traceback__)
            except RecursionError:
                raise exception

            self.logger.error(''.join(lines))

            return

        if isinstance(exception, commands.CheckFailure):
            await ctx.send("You are not authorised to use this command. ")
        elif isinstance(exception, commands.CommandOnCooldown):
            exception: commands.CommandOnCooldown
            await ctx.send(f'You\'re going too fast! Try again in {exception.retry_after:.2f} seconds.')

        elif isinstance(exception, commands.CommandNotFound):
            if isinstance(ctx.channel, discord.DMChannel):
                await ctx.send("Command not recognised!")

        elif isinstance(exception, commands.UserInputError):
            error = ' '.join(exception.args)
            error_data = re.findall('Converting to \"(.*)\" failed for parameter \"(.*)\"\.', error)
            if not error_data:
                await ctx.send('Huh? {}'.format(' '.join(exception.args)))
            else:
                if error_data[0][0][0] in 'aeiouAEIOU':
                    anindicator = 'n'
                else:
                    anindicator = ''
                await ctx.send(
                    'Huh? I thought `{1}` was supposed to be a{2} `{0}`...'.format(*error_data[0], anindicator))
        else:
            info = traceback.format_exception(type(exception), exception, exception.__traceback__, chain=False)
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
