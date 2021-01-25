import discord
from discord.ext import commands
import sqlite3

import openpotd
import shared


def select_two_problems(conn: sqlite3.Connection, userid):
    cursor = conn.cursor()
    cursor.execute('SELECT solves.problem_id FROM solves WHERE solves.id IN (SELECT id FROM solves WHERE'
                   ' solves.user = ? ORDER BY RANDOM() LIMIT 2)', (userid,))
    result = cursor.fetchall()

    return shared.POTD[result[0][0]], shared.POTD[result[0][1]]


class Ratings(commands.Cog):
    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot

    def rate_difficulty(self, ctx):
        problem_1, problem_2 = select_two_problems(self.bot.db, ctx.author.id)
        await ctx.send('Which of the following two problems do you think is **harder**?')


def setup(bot: openpotd.OpenPOTD):
    bot.add_cog(Ratings(bot))
