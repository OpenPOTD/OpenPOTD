import io
import sqlite3
from datetime import date

import discord
from discord.ext import commands
from discord.ext import flags
import re

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
        """Note: this is the admin version of the command so all problems are visible. """

        cursor = self.bot.db.cursor()
        potd_date, potd_id = None, None
        # Find the right potd for the user
        if potd.isdecimal():  # User passed in an id
            potd_id = potd
            cursor.execute('''SELECT "date" from problems WHERE problems.id = ?''', (potd_id,))
            result = cursor.fetchall()
            try:
                potd_date = result[0][0]
            except IndexError:
                await ctx.send('No such potd. ')
                return

        else:  # User passed in a date
            potd_date = potd
            cursor.execute('''SELECT id from problems WHERE date = ?''', (potd_date,))
            result = cursor.fetchall()
            if len(result) == 0:
                await ctx.send('No such POTD found. ')
                return
            else:
                potd_id = result[0][0]

        # Display the potd to the user
        cursor.execute('''SELECT image FROM images WHERE potd_id = ?''', (potd_id,))
        images = cursor.fetchall()
        if len(images) == 0:
            await ctx.send(f'POTD {potd_id} of {potd_date} has no picture attached. ')
        else:
            await ctx.send(f'POTD {potd_id} of {potd_date}', file=discord.File(io.BytesIO(images[0][0]),
                                                                               filename=f'POTD-{potd_id}-0.png'))
            for i in range(1, len(images)):
                await ctx.send(file=discord.File(io.BytesIO(images[i][0]), filename=f'POTD-{potd_id}-{i}.png'))

    @flags.add_flag('--date')
    @flags.add_flag('--season', type=int)
    @flags.add_flag('--statement')
    @flags.add_flag('--difficulty', type=int)
    @flags.add_flag('--answer', type=int)
    @flags.add_flag('--public', type=bool)
    @flags.command()
    async def update(self, ctx, potd: int, **flags):
        cursor = self.bot.db.cursor()
        if not flags['date'] is None and not bool(re.match(r'\d\d\d\d-\d\d-\d\d', flags['date'])):
            await ctx.send('Invalid date (specify yyyy-mm-dd)')
            return

        for param in flags:
            if flags[param] is not None:
                cursor.execute(f'UPDATE problems SET {param} = ? WHERE id = ?', (flags[param], potd))
        self.bot.db.commit()
        await ctx.send('Updated potd. ')


def setup(bot: commands.Bot):
    bot.add_cog(Management(bot))
