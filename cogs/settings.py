import discord
from discord.ext import commands

import openpotd


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

    @commands.command()
    async def nick(self, ctx, *, new_nick):
        if len(new_nick) > 32:
            await ctx.send('Nickname is too long!')
            return

        cursor = self.bot.db.cursor()
        cursor.execute('''INSERT OR IGNORE INTO users (discord_id, nickname, anonymous) VALUES (?, ?, ?)''',
                       (ctx.author.id, ctx.author.display_name, True))
        cursor.execute('UPDATE users SET nickname = ? WHERE discord_id = ?', (new_nick, ctx.author.id))
        self.bot.db.commit()

    @commands.command(name='self')
    async def userinfo(self, ctx):
        await ctx.send(embed=get_settings_embed(ctx.author.id, self.bot.db.cursor()))

    @commands.command()
    async def toggle_anon(self, ctx):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT anonymous from users where discord_id = ?', (ctx.author.id,))
        result = cursor.fetchall()

        if len(result) == 0:
            await ctx.send('You are not registered.')
        else:
            cursor.execute('UPDATE users SET anonymous = ? WHERE discord_id = ?', (not result[0][0], ctx.author.id))
            self.bot.db.commit()

        await ctx.send('Thank you! Your settings have been updated. Here are your new settings:',
                       embed=get_settings_embed(ctx.author.id, cursor))

    @commands.command()
    async def receive_medals(self, ctx, new_setting: bool):
        cursor = self.bot.db.cursor()
        cursor.execute('UPDATE users SET receiving_medal_roles = ? WHERE discord_id = ?', (new_setting, ctx.author.id))
        self.bot.db.commit()

        if cursor.rowcount == 1:
            await ctx.send('Changed successfully!')
        else:
            await ctx.send(f'No changes, either you are not registered or receive_medals '
                           f'was already set to {new_setting}. ')

        await ctx.send('Thank you! Your settings have been updated. Here are your new settings:',
                       embed=get_settings_embed(ctx.author.id, cursor))


def setup(bot: openpotd.OpenPOTD):
    bot.add_cog(Settings(bot))
