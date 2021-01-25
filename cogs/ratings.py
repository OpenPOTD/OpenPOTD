import discord
from discord.ext import commands
import sqlite3

import openpotd
import shared
import io

from dataclasses import dataclass
from datetime import datetime


def select_two_problems(conn: sqlite3.Connection, userid):
    cursor = conn.cursor()
    cursor.execute('SELECT solves.problem_id FROM solves WHERE solves.id IN (SELECT id FROM solves WHERE'
                   ' solves.user = ? ORDER BY RANDOM() LIMIT 2)', (userid,))
    result = cursor.fetchall()

    return shared.POTD(result[0][0], conn), shared.POTD(result[1][0], conn)


@dataclass
class ChoiceInformation:
    user: discord.User
    p1: shared.POTD
    p2: shared.POTD
    asked_time: datetime
    type: str


class Ratings(commands.Cog):
    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot
        self.waiting_for = {}

    @commands.command(brief="Grab two problems you've solved to compare the difficulty of. ")
    async def rate_difficulty(self, ctx):
        if ctx.author.id in self.waiting_for:
            await ctx.send('You are already trying to rate problems! If you want to cancel, use `%rate d`.')

        problem_1, problem_2 = select_two_problems(self.bot.db, ctx.author.id)
        await ctx.send('Which of the following two problems do you think is **harder**? \nProblem 1: ')

        for image in problem_1.images:
            await ctx.send(file=discord.File(io.BytesIO(image), filename='image.png'))

        await ctx.send('Problem 2: ')
        for image in problem_2.images:
            await ctx.send(file=discord.File(io.BytesIO(image), filename='image.png'))

        await ctx.send(f'Use `%rate OPTION` to submit your rating. Possible values for `OPTION` are: \n'
                       f'`1` if you thought the first problem was **harder**, \n'
                       f'`2` if you thought the second problem was **harder**, \n'
                       f'`n` if you think they are the same difficulty, or \n'
                       f'`d` if you have no preference (can\'t decide). ')

        self.waiting_for[ctx.author.id] = ChoiceInformation(ctx.author, problem_1, problem_2, datetime.now(), 'DIFF')

    @commands.command(brief="Grab two problems you've solved to compare the coolness of. ")
    async def rate_coolness(self, ctx):
        if ctx.author.id in self.waiting_for:
            await ctx.send('You are already trying to rate problems! If you want to cancel, use `%rate d`.')

        problem_1, problem_2 = select_two_problems(self.bot.db, ctx.author.id)
        await ctx.send('Which of the following two problems do you think is **cooler**? \nProblem 1: ')

        for image in problem_1.images:
            await ctx.send(file=discord.File(io.BytesIO(image), filename='image.png'))

        await ctx.send('Problem 2: ')
        for image in problem_2.images:
            await ctx.send(file=discord.File(io.BytesIO(image), filename='image.png'))

        await ctx.send(f'Use `%rate OPTION` to submit your rating. Possible values for `OPTION` are: \n'
                       f'`1` if you thought the first problem was **cooler**, \n'
                       f'`2` if you thought the second problem was **cooler**, \n'
                       f'`n` if you think they are the same difficulty, or \n'
                       f'`d` if you have no preference (can\'t decide). ')

        self.waiting_for[ctx.author.id] = ChoiceInformation(ctx.author, problem_1, problem_2, datetime.now(), 'COOL')


def setup(bot: openpotd.OpenPOTD):
    bot.add_cog(Ratings(bot))
