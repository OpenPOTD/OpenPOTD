import re

import discord
from discord.ext import commands
from discord.ext.commands import has_permissions

import openpotd


def in_guild(ctx: commands.Context):
    return ctx.guild is not None


class ServerConfig(commands.Cog):
    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot

    @commands.check(in_guild)
    @commands.command(brief='Prints configuration for this server')
    async def config(self, ctx: commands.Context):
        cursor = self.bot.db.cursor()
        server_id = ctx.guild.id

        cursor.execute('SELECT * from config WHERE server_id = ?', (server_id,))
        result = cursor.fetchall()

        if len(result) == 0:
            await ctx.send('No config found! Use init to initialise your server\'s configuration. ')
        else:
            embed = discord.Embed()
            result = result[0]
            embed.description = f'`1. potd_channel:` {result[1]} [<#{result[1]}>]\n' \
                                f'`2. ping_role_id:` {result[2]} [<@&{result[2]}>]\n' \
                                f'`3. solved_role_id:` {result[3]} [<@&{result[3]}>]\n' \
                                f'`4. otd_prefix:` {result[4]}\n' \
                                f'`5. command_prefix:` {result[5]}\n'
            await ctx.send(embed=embed)

    @commands.check(in_guild)
    @has_permissions(manage_guild=True)
    @commands.command(brief='Initialises the configuration (note this overwrites previous configuration)', name='init')
    async def init_cfg(self, ctx: commands.Context):
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
    @has_permissions(manage_guild=True)
    @commands.command(brief='Sets the potd channel')
    async def potd_channel(self, ctx, new: discord.TextChannel):
        if not new.guild.id == ctx.guild.id:
            await ctx.send("Please select a channel in **this** server! ")
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE config SET potd_channel = ? WHERE server_id = ?', (new.id, ctx.guild.id))
        self.bot.db.commit()
        await ctx.send('Set successfully!')

    @commands.check(in_guild)
    @has_permissions(manage_guild=True)
    @commands.command(brief='Sets the role to ping')
    async def ping_role(self, ctx, new: discord.Role):
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE config SET ping_role_id = ? WHERE server_id = ?', (new.id, ctx.guild.id))
        self.bot.db.commit()
        await ctx.send('Set successfully!')

    @commands.check(in_guild)
    @has_permissions(manage_guild=True)
    @commands.command(brief='Sets the role contestants get after solving the POTD')
    async def solved_role(self, ctx, new: discord.Role):
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE config SET solved_role_id = ? WHERE server_id = ?', (new.id, ctx.guild.id))
        self.bot.db.commit()
        await ctx.send('Set successfully!')

    @commands.check(in_guild)
    @has_permissions(manage_guild=True)
    @commands.command(brief='Sets the OTD prefix (some people like calling it a "QOTD" rather than a "POTD")')
    async def otd_prefix(self, ctx, new):
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE config SET otd_prefix = ? WHERE server_id = ?', (new, ctx.guild.id))
        self.bot.db.commit()
        await ctx.send('Set successfully!')

    @commands.check(in_guild)
    @has_permissions(manage_guild=True)
    @commands.command(brief='Sets the server command prefix')
    async def command_prefix(self, ctx, new):
        cursor = self.bot.db.cursor()
        openpotd.prefixes[ctx.guild.id] = new
        cursor.execute('UPDATE config SET command_prefix = ? WHERE server_id = ?', (new, ctx.guild.id))
        self.bot.db.commit()
        await ctx.send('Set successfully!')


def setup(bot: openpotd.OpenPOTD):
    bot.add_cog(ServerConfig(bot))
