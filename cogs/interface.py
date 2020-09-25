from discord.ext import commands


class Interface(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def register(self, ctx, *, season):
        cursor = self.bot.db.cursor()
        cursor.execute('''SELECT id from seasons where name = ? and server_id = ?''', (season, ctx.guild.id))
        ids = cursor.fetchall()
        if len(ids) == 0:
            await ctx.send('No such season!')
            return
        else:
            season_id = ids[0][0]
        cursor.execute('''INSERT OR IGNORE INTO users (discord_id) VALUES (?)''', (ctx.author.id,))

        cursor.execute('''SELECT EXISTS (SELECT 1 from registrations WHERE registrations.user_id = ? 
                            AND registrations.season_id = ?)''', (ctx.author.id, season_id))
        existence = cursor.fetchall()[0][0]
        if existence:
            await ctx.send("You've already signed up for this season!")
            return
        else:
            cursor.execute('''INSERT into registrations (user_id, season_id) VALUES (?, ?)''',
                           (ctx.author.id, season_id))
            await ctx.send(f"Registered you for {season}. ")
        self.bot.db.commit()


def setup(bot: commands.Bot):
    bot.add_cog(Interface(bot))
