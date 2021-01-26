import discord
from discord.ext import commands
import sqlite3
import logging

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
        self.logger = logging.getLogger('Ratings')

    @commands.command(brief="Rate two problems you've been given.", aliases=['rt', 'r'])
    async def rate(self, ctx, *, rating):
        if ctx.author.id not in self.waiting_for:
            await ctx.send("You haven't got any problems to rate! "
                           "Get some with `%rate_difficulty` or `%rate_coolness`.")
            return

        if rating not in ('1', '2', 'n', 'd'):
            await ctx.send("That's not a valid rating! Use `d` if you want to abandon ratings.")
            return

        choices: ChoiceInformation = self.waiting_for[ctx.author.id]
        cursor = self.bot.db.cursor()

        # Get number of ratings for each problem and calculate elo K value
        cursor.execute('SELECT COUNT() FROM rating_choices WHERE problem_1_id = ? OR problem_2_id = ? AND type = ?',
                       (choices.p1.id, choices.p1.id, choices.type))
        number_1 = cursor.fetchall()[0][0]
        elo_k_1 = 10 + 100 * 10 ** (number_1 / -20)
        cursor.execute('SELECT COUNT() FROM rating_choices WHERE problem_1_id = ? OR problem_2_id = ? AND type = ?',
                       (choices.p2.id, choices.p2.id, choices.type))
        number_2 = cursor.fetchall()[0][0]
        elo_k_2 = 10 + 100 * 10 ** (number_2 / -20)

        # Log rating
        cursor.execute('INSERT INTO rating_choices (problem_1_id, problem_2_id, choice, type, rater) '
                       'VALUES (?, ?, ?, ?, ?)',
                       (choices.p1.id, choices.p2.id, rating, choices.type, ctx.author.id))
        self.bot.db.commit()

        # If it doesn't care, void
        if rating == 'd':
            await ctx.send("Thank you for your rating.")
            return

        # Calculate elo stuffs
        s_value_1 = 1 if rating == '1' else 0.5 if rating == 'n' else 0
        s_value_2 = 1 - s_value_1

        if choices.type == 'DIFF':

            expected_1 = 1 / (1 + 10 ** ((choices.p2.difficulty_rating - choices.p1.difficulty_rating) / 400))
            expected_2 = 1 / (1 + 10 ** ((choices.p1.difficulty_rating - choices.p2.difficulty_rating) / 400))

            new_1 = choices.p1.difficulty_rating + elo_k_1 * (s_value_1 - expected_1)
            new_2 = choices.p2.difficulty_rating + elo_k_2 * (s_value_2 - expected_2)

            # Update the database
            cursor.executemany('UPDATE problems SET difficulty_rating = ? WHERE problems.id = ?',
                               [
                                   (new_1, choices.p1.id),
                                   (new_2, choices.p2.id)
                               ])
            self.bot.db.commit()

            old_1 = choices.p1.difficulty_rating
            old_2 = choices.p2.difficulty_rating

        elif choices.type == 'COOL':
            expected_1 = 1 / (1 + 10 ** ((choices.p2.coolness_rating - choices.p1.coolness_rating) / 400))
            expected_2 = 1 / (1 + 10 ** ((choices.p1.coolness_rating - choices.p2.coolness_rating) / 400))

            new_1 = choices.p1.coolness_rating + elo_k_1 * (s_value_1 - expected_1)
            new_2 = choices.p2.coolness_rating + elo_k_2 * (s_value_2 - expected_2)

            # Update the database
            cursor.executemany('UPDATE problems SET coolness_rating = ? WHERE problems.id = ?',
                               [
                                   (new_1, choices.p1.id),
                                   (new_2, choices.p2.id)
                               ])
            self.bot.db.commit()

            old_1 = choices.p1.coolness_rating
            old_2 = choices.p2.coolness_rating

        else:
            self.bot.logger.error(f'[RATING] No such type {choices.type}')
            return

        await ctx.send(f"Thank you for your rating. The ratings for the two problems were {old_1:.2f} and {old_2:.2f} "
                       f"respectively and they have changed to {new_1:.2f} and {new_2:.2f} respectively.")

        del self.waiting_for[ctx.author.id]

        self.logger.info(f'[RATE] User {choices.user.id} rated {choices.p1.id} and {choices.p2.id} PREFERENCE '
                         f'{rating} TYPE {choices.type}')

    @commands.command(brief="Grab two problems you've solved to compare the difficulty of. ", aliases=['rd'])
    async def rate_difficulty(self, ctx):
        if ctx.author.id in self.waiting_for:
            await ctx.send('You are already trying to rate problems! If you want to cancel, use `%rate d`.')
            return

        try:
            problem_1, problem_2 = select_two_problems(self.bot.db, ctx.author.id)
        except IndexError as e:
            await ctx.send("You need to have solved at least two problems!")
            return
        
        if len(problem_1.images) > 0:
            await ctx.send('Which of the following two problems do you think is **harder**? \nProblem 1: ',
                           file=discord.File(io.BytesIO(problem_1.images[0]), filename='image.png'))
        else:
            await ctx.send('Which of the following two problems do you think is **harder**? \nProblem 1: ')

        for image in problem_1.images[1:]:
            await ctx.send(file=discord.File(io.BytesIO(image), filename='image.png'))

        if len(problem_2.images) > 0:
            await ctx.send('Problem 2: ',
                           file=discord.File(io.BytesIO(problem_2.images[0]), filename='image.png'))
        else:
            await ctx.send('Problem 2: ')

        for image in problem_2.images[1:]:
            await ctx.send(file=discord.File(io.BytesIO(image), filename='image.png'))

        await ctx.send(f'Use `%rate OPTION` to submit your rating. Possible values for `OPTION` are: \n'
                       f'`1` if you thought the first problem was **harder**, \n'
                       f'`2` if you thought the second problem was **harder**, \n'
                       f'`n` if you think they are the same difficulty, or \n'
                       f'`d` if you have no preference (can\'t decide). ')

        self.waiting_for[ctx.author.id] = ChoiceInformation(ctx.author, problem_1, problem_2, datetime.now(), 'DIFF')

    @commands.command(brief="Grab two problems you've solved to compare the coolness of. ", aliases=['rq'])
    async def rate_quality(self, ctx):
        if ctx.author.id in self.waiting_for:
            await ctx.send('You are already trying to rate problems! If you want to cancel, use `%rate d`.')
            return

        try:
            problem_1, problem_2 = select_two_problems(self.bot.db, ctx.author.id)
        except IndexError as e:
            await ctx.send("You need to have solved at least two problems!")
            return

        if len(problem_1.images) > 0:
            await ctx.send('Which of the following two problems do you think is **cooler**? \nProblem 1: ',
                           file=discord.File(io.BytesIO(problem_1.images[0]), filename='image.png'))
        else:
            await ctx.send('Which of the following two problems do you think is **cooler**? \nProblem 1: ')

        for image in problem_1.images[1:]:
            await ctx.send(file=discord.File(io.BytesIO(image), filename='image.png'))

        if len(problem_2.images) > 0:
            await ctx.send('Problem 2: ',
                           file=discord.File(io.BytesIO(problem_2.images[0]), filename='image.png'))
        else:
            await ctx.send('Problem 2: ')

        for image in problem_2.images[1:]:
            await ctx.send(file=discord.File(io.BytesIO(image), filename='image.png'))

        await ctx.send(f'Use `%rate OPTION` to submit your rating. Possible values for `OPTION` are: \n'
                       f'`1` if you thought the first problem was **cooler**, \n'
                       f'`2` if you thought the second problem was **cooler**, \n'
                       f'`n` if you think they are the same quality, or \n'
                       f'`d` if you have no preference (can\'t decide). ')

        self.waiting_for[ctx.author.id] = ChoiceInformation(ctx.author, problem_1, problem_2, datetime.now(), 'COOL')


def setup(bot: openpotd.OpenPOTD):
    bot.add_cog(Ratings(bot))
