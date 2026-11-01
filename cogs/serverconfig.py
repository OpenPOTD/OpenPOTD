import re

import discord
from discord import app_commands
from discord.ext import commands

import openpotd
import shared


class ServerConfig(commands.Cog):
    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot

        # Replicate the old global blacklist check: no command may run for a
        # blacklisted user.
        for command in self.__cog_app_commands__:
            command.add_check(shared.not_blacklisted)

    @app_commands.command(description='Prints configuration for this server')
    @app_commands.guild_only()
    async def config(self, interaction: discord.Interaction):
        cursor = self.bot.db.cursor()
        server_id = interaction.guild.id

        cursor.execute('SELECT * from config WHERE server_id = ?', (server_id,))
        result = cursor.fetchall()

        if len(result) == 0:
            await interaction.response.send_message('No config found! Use init to initialise your server\'s '
                                                    'configuration. ', ephemeral=True)
        else:
            embed = discord.Embed()
            result = result[0]
            embed.description = f'`1. potd_channel:` {result[1]} [<#{result[1]}>]\n' \
                                f'`2. ping_role_id:` {result[2]} [<@&{result[2]}>]\n' \
                                f'`3. solved_role_id:` {result[3]} [<@&{result[3]}>]\n' \
                                f'`4. otd_prefix:` {result[4]}\n' \
                                f'`5. Bronze Role:` [<@&{result[6]}>]\n' \
                                f'`6. Silver Role:` [<@&{result[7]}>]\n' \
                                f'`7. Gold Role:` [<@&{result[8]}>]'
            await interaction.response.send_message(embed=embed)

    @app_commands.command(name='init',
                          description='Initialises the configuration (note this overwrites previous configuration)')
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def init_cfg(self, interaction: discord.Interaction):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT exists (select * from config where server_id = ?)', (interaction.guild.id,))

        guild: discord.Guild = interaction.guild
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

        if cursor.fetchall()[0][0]:
            # Just overwrite the entry
            cursor.execute('UPDATE config SET potd_channel = ?, ping_role_id = ?, solved_role_id = ?, otd_prefix = ?'
                           ' WHERE server_id = ?',
                           (qotd_channel_id, ping_role_id, solved_role_id, otd_prefix, guild.id))
        else:
            # Make a new entry
            cursor.execute('INSERT INTO config (potd_channel, ping_role_id, solved_role_id, otd_prefix, '
                           'server_id) VALUES (?, ?, ?, ?, ?)',
                           (qotd_channel_id, ping_role_id, solved_role_id, otd_prefix, guild.id))

        self.bot.db.commit()
        await interaction.response.send_message('Initialised the configuration for this server. ')

    @app_commands.command(description='Sets the potd channel')
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def potd_channel(self, interaction: discord.Interaction, new: discord.TextChannel):
        if not new.guild.id == interaction.guild.id:
            await interaction.response.send_message("Please select a channel in **this** server! ", ephemeral=True)
            return
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE config SET potd_channel = ? WHERE server_id = ?', (new.id, interaction.guild.id))
        self.bot.db.commit()
        await interaction.response.send_message('Set successfully!')

    @app_commands.command(description='Sets the role to ping')
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ping_role(self, interaction: discord.Interaction, new: discord.Role):
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE config SET ping_role_id = ? WHERE server_id = ?', (new.id, interaction.guild.id))
        self.bot.db.commit()
        await interaction.response.send_message('Set successfully!')

    @app_commands.command(description='Sets the role contestants get after solving the POTD')
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def solved_role(self, interaction: discord.Interaction, new: discord.Role):
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE config SET solved_role_id = ? WHERE server_id = ?', (new.id, interaction.guild.id))
        self.bot.db.commit()
        await interaction.response.send_message('Set successfully!')

    @app_commands.command(description='Sets the OTD prefix (some people like calling it a "QOTD" rather than a '
                                      '"POTD")')
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def otd_prefix(self, interaction: discord.Interaction, new: str):
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE config SET otd_prefix = ? WHERE server_id = ?', (new, interaction.guild.id))
        self.bot.db.commit()
        await interaction.response.send_message('Set successfully!')

    @app_commands.command(description='Sets the prize roles. ')
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def medal_roles(self, interaction: discord.Interaction, bronze: discord.Role, silver: discord.Role,
                          gold: discord.Role):
        cursor = self.bot.db.cursor()
        if not (bronze.guild == interaction.guild and silver.guild == interaction.guild
                and gold.guild == interaction.guild):
            await interaction.response.send_message('Invalid roles!', ephemeral=True)
            return
        cursor.execute('UPDATE config SET bronze_role_id = ?, silver_role_id = ?, gold_role_id = ? WHERE server_id = ?',
                       (bronze.id, silver.id, gold.id, interaction.guild.id))
        self.bot.db.commit()
        await interaction.response.send_message('Set successfully!')


async def setup(bot: openpotd.OpenPOTD):
    await bot.add_cog(ServerConfig(bot))
