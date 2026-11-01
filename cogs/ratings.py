import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import logging
import random

import openpotd
import shared
import io
import cogs.management as mgmt

from dataclasses import dataclass
from datetime import datetime


def select_two_problems(conn: sqlite3.Connection, interaction: discord.Interaction, field):
    cursor = conn.cursor()
    userid = interaction.user.id

    # Authorised members don't have to solve a problem to be able to rate it.
    if not mgmt.authorised(interaction):
        cursor.execute('SELECT solves.problem_id FROM solves WHERE solves.id IN (SELECT id FROM solves WHERE'
                       ' solves.user = ? ORDER BY RANDOM() LIMIT 1)', (userid,))
    else:
        cursor.execute('SELECT id from problems WHERE public = ? order by random() limit 1', (True,))

    first_problem_id = cursor.fetchall()[0][0]
    first_problem = shared.POTD(first_problem_id, conn)

    # Same with the second problem
    if not mgmt.authorised(interaction):
        cursor.execute('select problems.id from solves inner '
                       'join problems on solves.problem_id = problems.id where solves.id in (select id from '
                       f'solves where solves.user = ? and solves.problem_id != ?) order by abs(problems.{field} '
                       '- ?) LIMIT 20;',
                       (userid, first_problem_id,
                        first_problem.difficulty_rating if field == 'difficulty_rating'
                        else first_problem.coolness_rating))
    else:
        cursor.execute(f'SELECT id from problems where public = ? order by abs(problems.{field} - ?) limit 20',
                       (True,
                        first_problem.difficulty_rating if field == 'difficulty_rating'
                        else first_problem.coolness_rating))

    result = cursor.fetchall()
    second_problem_id = random.choice(result)[0]
    second_problem = shared.POTD(second_problem_id, conn)

    return first_problem, second_problem


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

        # Replicate the old global blacklist check: no command may run for a
        # blacklisted user.
        for command in self.__cog_app_commands__:
            command.add_check(shared.not_blacklisted)

    @app_commands.command(description="Rate two problems you've been given.")
    @app_commands.choices(rating=[
        app_commands.Choice(name='First problem', value='1'),
        app_commands.Choice(name='Second problem', value='2'),
        app_commands.Choice(name='They are the same', value='n'),
        app_commands.Choice(name='No preference', value='d'),
    ])
    async def rate(self, interaction: discord.Interaction, rating: app_commands.Choice[str]):
        rating = rating.value

        if interaction.user.id not in self.waiting_for:
            await interaction.response.send_message("You haven't got any problems to rate! "
                                                    "Get some with `/rate_difficulty` or `/rate_quality`.",
                                                    ephemeral=True)
            return

        choices: ChoiceInformation = self.waiting_for[interaction.user.id]
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
                       (choices.p1.id, choices.p2.id, rating, choices.type, interaction.user.id))
        self.bot.db.commit()

        # If it doesn't care, void
        if rating == 'd':
            await interaction.response.send_message("Thank you for your rating.")
            del self.waiting_for[interaction.user.id]
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
            await interaction.response.send_message('Something went wrong with your rating. ', ephemeral=True)
            return

        await interaction.response.send_message(f"Thank you for your rating. The ratings for the two problems were "
                                                f"{old_1:.2f} and {old_2:.2f} "
                                                f"respectively and they have changed to {new_1:.2f} and {new_2:.2f} "
                                                f"respectively.")

        del self.waiting_for[interaction.user.id]

        self.logger.info(f'[RATE] User {choices.user.id} rated {choices.p1.id} and {choices.p2.id} PREFERENCE '
                         f'{rating} TYPE {choices.type}')

    async def start_rating(self, interaction: discord.Interaction, field: str, type_str: str, comparison: str,
                           equality_noun: str):
        if interaction.user.id in self.waiting_for:
            await interaction.response.send_message('You are already trying to rate problems! If you want to cancel, '
                                                    'use `/rate` with the "No preference" option.', ephemeral=True)
            return

        try:
            problem_1, problem_2 = select_two_problems(self.bot.db, interaction, field)
        except IndexError:
            await interaction.response.send_message("You need to have solved at least two problems!", ephemeral=True)
            return

        if len(problem_1.images) > 0:
            await interaction.response.send_message(f'Which of the following two problems do you think is '
                                                    f'**{comparison}**? \nProblem 1: ',
                                                    file=discord.File(io.BytesIO(problem_1.images[0]),
                                                                      filename='image.png'))
        else:
            await interaction.response.send_message(f'Which of the following two problems do you think is '
                                                    f'**{comparison}**? \nProblem 1: ')

        for image in problem_1.images[1:]:
            await interaction.followup.send(file=discord.File(io.BytesIO(image), filename='image.png'))

        if len(problem_2.images) > 0:
            await interaction.followup.send('Problem 2: ',
                                            file=discord.File(io.BytesIO(problem_2.images[0]), filename='image.png'))
        else:
            await interaction.followup.send('Problem 2: ')

        for image in problem_2.images[1:]:
            await interaction.followup.send(file=discord.File(io.BytesIO(image), filename='image.png'))

        await interaction.followup.send(f'Use `/rate` to submit your rating. Possible values for `rating` are: \n'
                                        f'`First problem` if you thought the first problem was **{comparison}**, \n'
                                        f'`Second problem` if you thought the second problem was **{comparison}**, \n'
                                        f'`They are the same` if you think they are the same {equality_noun}, or \n'
                                        f'`No preference` if you have no preference (can\'t decide). ')

        self.waiting_for[interaction.user.id] = ChoiceInformation(interaction.user, problem_1, problem_2,
                                                                  shared.utc_now(), type_str)

    @app_commands.command(description="Grab two problems you've solved to compare the difficulty of. ")
    async def rate_difficulty(self, interaction: discord.Interaction):
        await self.start_rating(interaction, 'difficulty_rating', 'DIFF', 'harder', 'difficulty')

    @app_commands.command(description="Grab two problems you've solved to compare the coolness of. ")
    async def rate_quality(self, interaction: discord.Interaction):
        await self.start_rating(interaction, 'coolness_rating', 'COOL', 'cooler', 'quality')

    @app_commands.command(description="Randomly do either rate_quality or rate_difficulty")
    async def rate_random(self, interaction: discord.Interaction):
        field, type_str, comparison, equality_noun = random.choice(
            [
                ('coolness_rating', 'COOL', 'cooler', 'quality'),
                ('difficulty_rating', 'DIFF', 'harder', 'difficulty'),
            ])
        await self.start_rating(interaction, field, type_str, comparison, equality_noun)


async def setup(bot: openpotd.OpenPOTD):
    await bot.add_cog(Ratings(bot))
