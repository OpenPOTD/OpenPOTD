from discord.ext import commands
from datetime import date


class Management(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def newseason(self, ctx, *, name):
        cursor = self.bot.db.cursor()
        cursor.execute('''INSERT INTO seasons (running, name) VALUES (?, ?)''', (False, name))
        self.bot.db.commit()
        cursor.execute('''SELECT LAST_INSERT_ROWID()''')
        rowid = cursor.fetchone()[0]
        await ctx.send(f'Added a new season called `{name}` with id `{rowid}`. ')

    @commands.command()
    async def add(self, ctx, season: int, prob_date, answer, *, statement):
        cursor = self.bot.db.cursor()
        prob_date_parsed = date.fromisoformat(prob_date)
        cursor.execute('''INSERT INTO problems ("date", season, statement, answer) VALUES (?, ?, ?, ?)''',
                       (prob_date_parsed, season, statement, answer))
        self.bot.db.commit()
        await ctx.send('Added problem. ')

def setup(bot: commands.Bot):
    bot.add_cog(Management(bot))