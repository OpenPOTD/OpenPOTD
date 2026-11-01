import discord
from discord import app_commands
from discord.ext import commands

import openpotd
import shared


def get_settings_embed(userid, cursor):
    embed = discord.Embed()

    # Retrieve nickname information
    cursor.execute('SELECT nickname, anonymous, receiving_medal_roles from users where discord_id = ?',
                   (userid,))
    result = cursor.fetchall()
    if len(result) > 0:
        embed.add_field(name='Nickname', value=result[0][0])
        embed.add_field(name='Anonymous', value=result[0][1])
        embed.add_field(name='Receiving Medal Roles', value=result[0][2])
    else:
        embed.add_field(name='Nickname', value='None')

    return embed


class Settings(commands.Cog):
    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot

        # Replicate the old global blacklist check: no command may run for a
        # blacklisted user.
        for command in self.__cog_app_commands__:
            command.add_check(shared.not_blacklisted)

    @app_commands.command(description='Sets your nickname. ')
    async def nick(self, interaction: discord.Interaction, new_nick: str):
        if len(new_nick) > 32:
            await interaction.response.send_message('Nickname is too long!', ephemeral=True)
            return

        cursor = self.bot.db.cursor()
        cursor.execute('''INSERT OR IGNORE INTO users (discord_id, nickname, anonymous) VALUES (?, ?, ?)''',
                       (interaction.user.id, interaction.user.display_name, True))
        cursor.execute('UPDATE users SET nickname = ? WHERE discord_id = ?', (new_nick, interaction.user.id))
        self.bot.db.commit()
        await interaction.response.send_message('Done!', ephemeral=True)

    @app_commands.command(name='self', description='Shows your current settings. ')
    async def userinfo(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=get_settings_embed(interaction.user.id, self.bot.db.cursor()))

    @app_commands.command()
    async def toggle_anon(self, interaction: discord.Interaction):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT anonymous from users where discord_id = ?', (interaction.user.id,))
        result = cursor.fetchall()

        if len(result) == 0:
            await interaction.response.send_message('You are not registered.', ephemeral=True)
        else:
            cursor.execute('UPDATE users SET anonymous = ? WHERE discord_id = ?', (not result[0][0], interaction.user.id))
            self.bot.db.commit()
            await interaction.response.send_message('Thank you! Your settings have been updated. Here are your new settings:',
                                                    embed=get_settings_embed(interaction.user.id, cursor))

    @app_commands.command()
    async def receive_medals(self, interaction: discord.Interaction, new_setting: bool):
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE users SET receiving_medal_roles = ? WHERE discord_id = ?',
                       (new_setting, interaction.user.id))
        self.bot.db.commit()

        if cursor.rowcount == 1:
            await interaction.response.send_message('Changed successfully!')
            ephemeral = False
        else:
            await interaction.response.send_message(f'No changes, either you are not registered or receive_medals '
                                                    f'was already set to {new_setting}. ', ephemeral=True)
            ephemeral = True

        await interaction.followup.send('Thank you! Your settings have been updated. Here are your new settings:',
                                        embed=get_settings_embed(interaction.user.id, cursor), ephemeral=ephemeral)


async def setup(bot: openpotd.OpenPOTD):
    await bot.add_cog(Settings(bot))
