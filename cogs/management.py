import io
import sqlite3
from datetime import date

from discord.ext import commands


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

    @commands.command()
    async def linkimg(self, ctx, potd: int):
        if len(ctx.message.attachments) < 1:
            await ctx.send("No attached file. ")
            return
        else:
            save_path = io.BytesIO()
            await ctx.message.attachments[0].save(save_path)
            cursor = self.bot.db.cursor()
            cursor.execute('''INSERT INTO images (potd_id, image) VALUES (?, ?)''',
                           (potd, sqlite3.Binary(save_path.getbuffer())))
            self.bot.db.commit()
            save_path.close()


    @commands.command()
    async def showpotd(self, ctx, potd):
        cursor = self.bot.db.cursor()
        # Find the right potd for the user
        if potd.isdecimal():  # User passed in an id
            id = potd
        else:   # User passed in a date, we expect ISO format
            try:
                potd_date = date.fromisoformat(potd)
            except ValueError:
                await ctx.send('Incorrect date format. Please enter your date in ISO format (like 2020-09-01 '
                               'for the first of September).')
                return
            cursor.execute('''SELECT id from problems WHERE date = "?" AND public = "?"''', (potd_date, True))
            result = cursor.fetchall()
            if len(result) == 0:
                await ctx.send('No such POTD found. ')
                return
            else:
                id = result[0][0]

        # Display the potd to the user
        cursor.execute('''SELECT image FROM images WHERE potd_id = ?''', (id, ))
        images = cursor.fetchall()
        if len(images) == 0:
            await ctx.send(f'POTD {id} has no picture attached. ')
        else:
            await ctx.send(f'POTD {id}', file=io.BytesIO(images[0][0]))
            for i in range(1, len(images)):
                await ctx.send(file=io.BytesIO(images[i][0]))


def setup(bot: commands.Bot):
    bot.add_cog(Management(bot))
