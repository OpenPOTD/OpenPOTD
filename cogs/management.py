import io
import re
import sqlite3
from datetime import date
from datetime import datetime

import discord
import schedule
from discord.ext import commands
from discord.ext import flags

import openpotd

authorised_set = set()

def authorised(ctx):
    return ctx.author.id in authorised_set

class Management(commands.Cog):

    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot
        schedule.every().day.at('17:17').do(self.schedule_potd)
        global authorised_set
        authorised_set = self.bot.config['authorised']

    def schedule_potd(self):
        self.bot.loop.create_task(self.advance_potd())

    async def advance_potd(self):
        print(f'Advancing POTD at {datetime.now()}')
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT problems.id from (seasons left join problems on seasons.running = True '
                       'and seasons.id = problems.season and problems.date = ? )', (str(date.today()),))
        result = cursor.fetchall()
        potd_channel = self.bot.get_channel(self.bot.config['potd_channel'])
        if len(result) == 0 or result[0][0] is None:
            await potd_channel.send('Sorry! We are running late on the potd today. ')
            return

        # Send the potd
        potd_id = result[0][0]
        cursor.execute('SELECT images.image from images where images.potd_id = ?', (potd_id,))
        images = cursor.fetchall()
        if len(images) == 0:
            await potd_channel.send(f'POTD {potd_id} of {str(date.today())} has no picture attached. ')
        else:
            await potd_channel.send(f'POTD {potd_id} of {str(date.today())}',
                                    file=discord.File(io.BytesIO(images[0][0]),
                                                      filename=f'POTD-{potd_id}-0.png'))
            for i in range(1, len(images)):
                await potd_channel.send(file=discord.File(io.BytesIO(images[i][0]), filename=f'POTD-{potd_id}-{i}.png'))

        # Advance the season
        cursor.execute('SELECT season FROM problems WHERE id = ?', (potd_id,))
        season_id = cursor.fetchall()[0][0]
        cursor.execute('UPDATE seasons SET latest_potd = ? WHERE id = ?', (potd_id, season_id))

        # Make the new potd publically available
        cursor.execute('UPDATE problems SET public = ? WHERE id = ?', (True, potd_id))

        # Commit db
        self.bot.db.commit()

    @commands.command()
    @commands.check(authorised)
    async def newseason(self, ctx, *, name):
        cursor = self.bot.db.cursor()
        cursor.execute('''INSERT INTO seasons (running, name) VALUES (?, ?)''', (False, name))
        self.bot.db.commit()
        cursor.execute('''SELECT LAST_INSERT_ROWID()''')
        rowid = cursor.fetchone()[0]
        await ctx.send(f'Added a new season called `{name}` with id `{rowid}`. ')

    @commands.command()
    @commands.check(authorised)
    async def add(self, ctx, season: int, prob_date, answer, *, statement):
        cursor = self.bot.db.cursor()
        prob_date_parsed = date.fromisoformat(prob_date)
        cursor.execute('''INSERT INTO problems ("date", season, statement, answer) VALUES (?, ?, ?, ?)''',
                       (prob_date_parsed, season, statement, answer))
        self.bot.db.commit()
        await ctx.send('Added problem. ')

    @commands.command()
    @commands.check(authorised)
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
    @commands.check(authorised)
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
    @commands.check(authorised)
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

    @commands.command()
    @commands.check(authorised)
    async def info(self, ctx, potd):
        cursor = self.bot.db.cursor()
        if potd.isdecimal():
            cursor.execute('SELECT * FROM problems WHERE id = ?', (int(potd),))
        else:
            cursor.execute('SELECT * FROM problems WHERE date = ?', (potd,))

        result = cursor.fetchall()
        if len(result) == 0:
            await ctx.send('No such potd. ')
            return

        columns = ['id', 'date', 'season', 'statement',
                   'difficulty', 'weighted_solves', 'base_points', 'answer', 'public']
        embed = discord.Embed(title=f'POTD {result[0][0]}')
        for i in range(len(columns)):
            embed.add_field(name=columns[i], value=result[0][i], inline=False)
        await ctx.send(embed=embed)


def setup(bot: openpotd.OpenPOTD):
    bot.add_cog(Management(bot))
