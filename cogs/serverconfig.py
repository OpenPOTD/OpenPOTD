import re

import discord
from discord.ext import commands

import openpotd


def in_guild(ctx: commands.Context):
    return ctx.guild is not None


class ServerConfig(commands.Cog):
    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot

    @commands.check(in_guild)
    @commands.command(brief='Prints configuration for this server')
    def config(self, ctx: commands.Context):
        cursor = self.bot.db.cursor()
        server_id = ctx.guild.id

        cursor.execute('SELECT * from config WHERE server_id = ?', (server_id,))
        result = cursor.fetchall()

        if len(result) == 0:
            await ctx.send('No config found! Use init to initialise your server\'s configuration. ')
        else:
            embed = discord.Embed()
            embed.description = f'`1. potd_channel:` {result[1]} [<#{result[1]}>]' \
                                f'`2. ping_role_id:` {result[2]} [<@&{result[2]}>]' \
                                f'`3. solved_role_id:` {result[3]} [<@&{result[3]}>]' \
                                f'`4. otd_prefix:` {result[4]}' \
                                f'`5. command_prefix:` {result[5]}'
            await ctx.send(embed=embed)

    @commands.check(in_guild)
    @commands.command(brief='Initialises the configuration (note this overwrites previous configuration)', name='init')
    def init_cfg(self, ctx: commands.Context):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT exists (select * from config where server_id = ?)', (ctx.guild.id,))

        guild: discord.Guild = ctx.guild
        channels = guild.text_channels

        # "Infer" the qotd posting channel
        for channel in channels:
            if bool(re.match('^.*-of-the-day$', channel.name)):
                qotd_channel_id = channel.id
                break
        else:
            qotd_channel_id = None

        # "Infer" the qotd role to ping
        for role in guild.roles:
            if bool(re.match('^.*-of-the-day$', role.name)) or bool(re.match('^.otd$', role.name)):
                ping_role_id = role.id
                break
        else:
            ping_role_id = None

        # "Infer" the solved role
        for role in guild.roles:
            if bool(re.match('^.*-solved$', role.name)):
                solved_role_id = role.id
                break
        else:
            solved_role_id = None

        otd_prefix = self.bot.config['otd_prefix']
        command_prefix = self.bot.config['prefix']

        if cursor.fetchall()[0][0]:
            # Just overwrite the entry
            cursor.execute('UPDATE config SET potd_channel = ?, ping_role_id = ?, solved_role_id = ?, otd_prefix = ?'
                           ', command_prefix = ? WHERE server_id = ?',
                           (qotd_channel_id, ping_role_id, solved_role_id, otd_prefix, command_prefix, guild.id))
        else:
            # Make a new entry
            cursor.execute('INSERT INTO config (potd_channel, ping_role_id, solved_role_id, otd_prefix, '
                           'command_prefix, server_id) VALUES (?, ?, ?, ?, ?, ?)',
                           (qotd_channel_id, ping_role_id, solved_role_id, otd_prefix, command_prefix, guild.id))

        self.bot.db.commit()

    @commands.check(in_guild)
    @commands.command(brief='Sets a config variable (use the config variable number printed with config)')
    async def set(self, ctx, var: int, new):
        cursor = self.bot.db.cursor()
        if var not in range(1, 6):
            await ctx.send('Invalid config variable!')
            return

        if var == 1:
            if new in [channel.id for channel in ctx.guild.text_channels]:
                cursor.execute('UPDATE config SET potd_channel = ? WHERE server_id = ?', (new, ctx.guild.id))
                self.bot.db.commit()
                await ctx.send('Set successfully!')
                return
            else:
                await ctx.send('No such channel! Please enter the ID of ')

    async def potd_channel(self, ctx, new: discord.TextChannel):
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE config SET potd_channel = ? WHERE server_id = ?', (new.id, ctx.guild.id))
        self.bot.db.commit()
        await ctx.send('Set successfully!')

    async def ping_role(self, ctx, new: discord.Role):
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE config SET ping_role_id = ? WHERE server_id = ?', (new.id, ctx.guild.id))
        self.bot.db.commit()
        await ctx.send('Set successfully!')

    async def solved_role(self, ctx, new: discord.Role):
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE config SET solved_role_id = ? WHERE server_id = ?', (new.id, ctx.guild.id))
        self.bot.db.commit()
        await ctx.send('Set successfully!')

    async def otd_prefix(self, ctx, new):
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE config SET otd_prefix = ? WHERE server_id = ?', (new, ctx.guild.id))
        self.bot.db.commit()
        await ctx.send('Set successfully!')

    async def command_prefix(self, ctx, new):
        cursor = self.bot.db.cursor()
        openpotd.prefixes[ctx.guild.id] = new
        cursor.execute('UPDATE config SET command_prefix = ? WHERE server_id = ?', (new, ctx.guild.id))
        self.bot.db.commit()
        await ctx.send('Set successfully!')


def setup(bot: openpotd.OpenPOTD):
    bot.add_cog(ServerConfig(bot))
