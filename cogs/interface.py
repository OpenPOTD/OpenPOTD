import io
import logging
import math
from datetime import datetime
import datetime as dt
import random

import discord
from discord.ext import commands

import openpotd
import shared


# Change this if you want a different algorithm
def weighted_score(attempts: int):
    return 0.9 ** (attempts - 1)


class Interface(commands.Cog):
    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot
        self.logger = logging.getLogger('interface')
        self.cooldowns = {}

    @commands.command()
    @commands.check(lambda ctx: False)  # This command is disabled since it only applies for multi-server config
    async def register(self, ctx, *, season):
        cursor = self.bot.db.cursor()
        cursor.execute('''SELECT id from seasons where name = ? and server_id = ?''', (season, ctx.guild.id))
        ids = cursor.fetchall()
        if len(ids) == 0:
            await ctx.send('No such season!')
            return
        else:
            season_id = ids[0][0]
        cursor.execute('''INSERT OR IGNORE INTO users (discord_id, nickname, anonymous) VALUES (?, ?, ?)''',
                       (ctx.author.id, ctx.author.display_name, True))

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

    def update_rankings(self, season: int, potd_id: int = -1):
        cursor = self.bot.db.cursor()

        # Get all solves this season
        cursor.execute('select solves.user, solves.problem_id, solves.num_attempts from problems left join solves '
                       'where problems.season = ? and problems.id = solves.problem_id and official = ?', (season, True))
        solves = cursor.fetchall()

        # Get weighted attempts for each problem
        weighted_attempts = {}
        for solve in solves:
            if solve[1] in weighted_attempts:
                weighted_attempts[solve[1]] += weighted_score(solve[2])
            else:
                weighted_attempts[solve[1]] = weighted_score(solve[2])

        # Calculate how many points each problem should be worth on the 1st attempt
        problem_points = {i: self.bot.config['base_points'] / weighted_attempts[i] for i in weighted_attempts}

        # Get all ranked people
        cursor.execute('select user_id from rankings where season_id = ?', (season,))
        ranked_users = cursor.fetchall()

        # Calculate scores of each person
        total_score = {user[0]: 0 for user in ranked_users}
        for solve in solves:
            total_score[solve[0]] += problem_points[solve[1]] * weighted_score(solve[2])

        # Log stuff
        self.logger.info('Updating rankings')

        if potd_id == -1:
            # Then we shall update all the potds
            cursor.executemany('UPDATE problems SET weighted_solves = ?, base_points = ? WHERE problems.id = ?',
                               [(weighted_attempts[i], problem_points[i], i) for i in weighted_attempts])
        else:
            # Only update the specified potd
            if potd_id in weighted_attempts:
                cursor.execute('UPDATE problems SET weighted_solves = ?, base_points = ? WHERE problems.id = ?',
                               (weighted_attempts[potd_id], problem_points[potd_id], potd_id))
            else:
                self.logger.error(f'No potd with id {potd_id} present. Cannot refresh stats [update_rankings]')

        # Prepare data to be put into the db
        total_score_list = [(i, total_score[i]) for i in total_score]
        total_score_list.sort(key=lambda x: -x[1])
        cursor.executemany('update rankings SET rank = ?, score = ? WHERE user_id = ? and season_id = ?',
                           [(i + 1, total_score_list[i][1], total_score_list[i][0], season) for i in
                            range(len(total_score_list))])

        # Commit
        self.bot.db.commit()

    async def update_embed(self, potd_id: int):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT config.server_id, potd_channel, otd_prefix, message_id from config left join '
                       'stats_messages ON config.server_id = stats_messages.server_id WHERE stats_messages.id '
                       'is NOT NULL and stats_messages.potd_id = ?;', (potd_id,))
        servers = cursor.fetchall()

        problem = shared.POTD(potd_id, self.bot.db)

        for server_data in servers:
            potd_channel: discord.TextChannel = self.bot.get_channel(server_data[1])
            if potd_channel is not None:
                try:
                    stats_message = await potd_channel.fetch_message(server_data[3])
                    embed = problem.build_embed(self.bot.db, False, server_data[2])
                    await stats_message.edit(embed=embed)
                except discord.errors.NotFound as e:
                    self.logger.warning(f'[UPDATE_EMBED] Server {server_data[0]} no message id {server_data[3]}')

    def refresh(self, season: int, potd_id: int):
        # Update the rankings in the db
        self.update_rankings(season, potd_id)

        # Update the embed showing stats
        self.bot.loop.create_task(self.update_embed(potd_id))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is not None or message.author.id == self.bot.user.id \
                or message.content[0] == self.bot.config['prefix']:  # you can't submit answers in a server
            return

        # Make sure it's time for submission
        if self.bot.posting_problem:
            await message.channel.send('The new problem is being posted. Please wait until the bot '
                                       'status changes to submit your answer. ')
            return

        # Validating int-ness
        s = message.content
        if not (s[1:].isdecimal() if s[0] in ('-', '+') else s.isdecimal()):
            await message.channel.send('Please provide an integer answer! ')
            return
        else:
            answer = int(s)

        # Check that it isn't too big or too small
        if not -9223372036854775808 <= answer <= 9223372036854775807:
            await message.channel.send('Your answer is not a 64 bit signed integer (between -2^63 and 2^63 - 1). '
                                       'Please try again. ')
            return

        cursor = self.bot.db.cursor()

        # Check cooldowns
        if self.bot.config['cooldown']:
            if message.author.id in self.cooldowns and self.cooldowns[message.author.id] > datetime.utcnow():
                await message.channel.send(f"You're on cooldown! Send another answer in "
                                           f"{(self.cooldowns[message.author.id] - datetime.utcnow()).total_seconds():.2f} seconds. ")
                return

        # Get the current answer from the database
        cursor.execute('SELECT answer, problems.id, seasons.id from seasons left join problems '
                       'where seasons.running = ? and problems.id = seasons.latest_potd', (True,))
        correct_answer_list = cursor.fetchall()

        # Make sure the user is registered
        cursor.execute('''INSERT OR IGNORE INTO users (discord_id, nickname, anonymous) VALUES (?, ?, ?)''',
                       (message.author.id, message.author.display_name, True))
        self.bot.db.commit()

        if len(correct_answer_list) == 0:
            await message.channel.send(
                f'There is no current {self.bot.config["otd_prefix"]}OTD to check answers against. ')
            return
        else:
            correct_answer, potd_id, season_id = correct_answer_list[0][0], correct_answer_list[0][1], \
                                                 correct_answer_list[0][2]

            if self.bot.config['cooldown']:
                cursor.execute('SELECT count() from attempts where user_id = ? and potd_id = ?',
                               (message.author.id, potd_id))
                num_attempts = cursor.fetchall()[0][0]
                cool_down = math.pow(1.75, num_attempts)
                self.cooldowns[message.author.id] = datetime.utcnow() + dt.timedelta(seconds=cool_down)

            # Put a ranking entry in for them
            cursor.execute('INSERT or IGNORE into rankings (season_id, user_id) VALUES (?, ?)',
                           (season_id, message.author.id,))
            self.bot.db.commit()

            # Check that they have not already solved this problem
            cursor.execute('SELECT exists (select 1 from solves where problem_id = ? and solves.user = ?)',
                           (potd_id, message.author.id))
            if cursor.fetchall()[0][0]:
                await message.channel.send(f'You have already solved this {self.bot.config["otd_prefix"].lower()}otd! ')
                return

            # We got to record the submission anyway even if it is right or wrong
            try:
                cursor.execute('INSERT into attempts (user_id, potd_id, official, submission, submit_time) '
                               'VALUES (?, ?, ?, ?, ?)',
                               (message.author.id, potd_id, True, int(message.content), datetime.utcnow()))
                self.bot.db.commit()
            except OverflowError:
                cursor.execute('INSERT into attempts (user_id, potd_id, official, submission, submit_time '
                               'VALUES (?, ?, ?, ?, ?)',
                               (message.author.id, potd_id, True, -1000, datetime.utcnow()))
                self.bot.db.commit()

            # Calculate the number of attempts
            cursor.execute('SELECT count(1) from attempts where attempts.potd_id = ? and attempts.user_id = ?',
                           (potd_id, message.author.id))
            num_attempts = cursor.fetchall()[0][0]

            if answer == correct_answer:  # Then the answer is correct. Let's give them points.
                # Insert data
                cursor.execute('INSERT into solves (user, problem_id, num_attempts, official) VALUES (?, ?, ?, ?)',
                               (message.author.id, potd_id, num_attempts, True))
                self.bot.db.commit()

                # Recalculate scoreboard
                self.refresh(season_id, potd_id)

                # Alert user that they got the question correct
                if random.random() < 0.05:
                    await message.channel.send(
                        f'Correct answer, good shooting Question Hunter! Attempts: `{num_attempts}`')
                else:
                    await message.channel.send(f'Thank you! You solved the problem after {num_attempts} attempts. ')

                # Give them the "solved" role
                cursor.execute('SELECT server_id, solved_role_id from config where solved_role_id is not null')
                servers = cursor.fetchall()

                for server in servers:
                    guild: discord.Guild = self.bot.get_guild(server[0])
                    if guild is None:
                        continue

                    member: discord.Member = guild.get_member(message.author.id)
                    if member is None:
                        continue

                    solved_role: discord.Role = guild.get_role(server[1])
                    if solved_role is None:
                        continue

                    try:
                        await member.add_roles(solved_role, reason=f'Solved POTD')
                    except Exception as e:
                        self.logger.warning(e)

                # Logged that they solved it
                self.logger.info(
                    f'User {message.author.id} just solved {self.bot.config["otd_prefix"].lower()}otd {potd_id}. ')

            else:
                # They got it wrong
                await message.channel.send(f'You did not solve this problem! Number of attempts: `{num_attempts}`. ')

                # Recalculate stuff anyway
                self.refresh(season_id, potd_id)

                # Log that they didn't solve it
                self.logger.info(
                    f'User {message.author.id} submitted incorrect answer {answer} for {self.bot.config["otd_prefix"].lower()}otd {potd_id}. ')

    @commands.command()
    async def score(self, ctx, season: int = None):
        cursor = self.bot.db.cursor()
        if season is None:
            cursor.execute('SELECT id, name from seasons where running = ?', (True,))
            running_seasons = cursor.fetchall()
            if len(running_seasons) == 0:
                await ctx.send('No current running season. Please specify a season. ')
                return
            else:
                season = running_seasons[0][0]
                szn_name = running_seasons[0][1]
        else:
            cursor.execute('SELECT id, name from seasons where id = ?', (season,))
            selected_seasons = cursor.fetchall()
            if len(selected_seasons) == 0:
                await ctx.send(f'No season with id {season}. Please specify a valid season. ')
                return
            else:
                season = selected_seasons[0][0]
                szn_name = selected_seasons[0][1]

        cursor.execute('SELECT rank, score from rankings where season_id = ? and user_id = ?', (season, ctx.author.id))
        rank = cursor.fetchall()
        if len(rank) == 0:
            await ctx.send('You are not ranked in this season!')
        else:
            embed = discord.Embed(title=f'{szn_name} ranking for {ctx.author.name}')
            if rank[0][0] <= 3:
                colours = [0xc9b037, 0xd7d7d7, 0xad8a56]  # gold, silver, bronze
                embed.colour = discord.Color(colours[rank[0][0] - 1])
            else:
                embed.colour = discord.Color(0xffffff)
            embed.add_field(name='Rank', value=rank[0][0])
            embed.add_field(name='Score', value=f'{rank[0][1]:.2f}')
            await ctx.send(embed=embed)

    @commands.command()
    async def rank(self, ctx, season: int = None):
        cursor = self.bot.db.cursor()
        if season is None:
            cursor.execute('SELECT id, name from seasons where running = ?', (True,))
            running_seasons = cursor.fetchall()
            if len(running_seasons) == 0:
                await ctx.send('No current running season. Please specify a season. ')
                return
            else:
                season = running_seasons[0][0]
                szn_name = running_seasons[0][1]
        else:
            cursor.execute('SELECT id, name from seasons where id = ?', (season,))
            selected_seasons = cursor.fetchall()
            if len(selected_seasons) == 0:
                await ctx.send(f'No season with id {season}. Please specify a valid season. ')
                return
            else:
                season = selected_seasons[0][0]
                szn_name = selected_seasons[0][1]

        cursor.execute('SELECT rank, score, user_id from rankings where season_id = ? order by rank', (season,))
        rankings = cursor.fetchall()

        if len(rankings) <= 20:
            # If there are less than 20 rankings, we don't need a whole menu (in fact dpymenus will throw us an error)
            embed = discord.Embed(title=f'{szn_name} rankings')
            scores = '\n'.join([f'{rank}. {score:.2f} [<@!{user_id}>]' for (rank, score, user_id) in rankings])
            embed.description = scores
            await ctx.send(embed=embed)
        else:
            pages = []
            for i in range(len(rankings) // 20 + 1):
                page = discord.Embed(title=f'{szn_name} rankings - Page {i + 1}')
                scores = '\n'.join(
                    [f'{rank}. {score:.2f} [<@!{user_id}>]' for (rank, score, user_id) in rankings[20 * i:20 * i + 20]])
                page.description = scores
                pages.append(page)
            await self.bot.get_cog('MenuManager').new_menu(ctx, pages)

    @commands.command()
    async def fetch(self, ctx, *, problem: shared.POTD):
        if not await problem.ensure_public(ctx):
            return

        potd_id = problem.id

        cursor = self.bot.db.cursor()
        cursor.execute('SELECT date from problems where id = ?', (potd_id,))
        potd_date = cursor.fetchall()[0][0]

        # Display the potd to the user
        cursor.execute('''SELECT image FROM images WHERE potd_id = ?''', (potd_id,))
        images = cursor.fetchall()
        if len(images) == 0:
            await ctx.send(f'{self.bot.config["otd_prefix"]}OTD {potd_id} of {potd_date} has no picture attached. ')
        else:
            await ctx.send(f'{self.bot.config["otd_prefix"]}OTD {potd_id} of {potd_date}',
                           file=discord.File(io.BytesIO(images[0][0]),
                                             filename=f'POTD-{potd_id}-0.png'))
            for i in range(1, len(images)):
                await ctx.send(file=discord.File(io.BytesIO(images[i][0]), filename=f'POTD-{potd_id}-{i}.png'))

        # Log this stuff
        self.logger.info(
            f'User {ctx.author.id} requested {self.bot.config["otd_prefix"]}OTD with date {potd_date} and number {potd_id}. ')

    @commands.command()
    async def check(self, ctx, problem: shared.POTD, answer: int):
        if not await problem.ensure_public(ctx):
            return

        cursor = self.bot.db.cursor()
        potd_id = problem.id

        # Check that it's not part of a currently running season.
        cursor.execute('SELECT name from seasons where latest_potd = ?', (potd_id,))
        seasons = cursor.fetchall()
        if len(seasons) > 0:
            await ctx.send(f'This {self.bot.config["otd_prefix"].lower()}otd is part of {seasons[0][0]}. '
                           f'Please just DM your answer for this {self.bot.config["otd_prefix"]}OTD to me. ')
            return

        # Get the correct answer
        cursor.execute('SELECT answer from problems where id = ?', (potd_id,))
        correct_answer = cursor.fetchall()[0][0]
        answer_is_correct = correct_answer == answer

        # See whether they've solved it before
        cursor.execute('SELECT exists (select * from solves where solves.user = ? and solves.problem_id = ?)',
                       (ctx.author.id, potd_id))
        solved_before = cursor.fetchall()[0][0]

        # Make sure the user is registered
        cursor.execute('''INSERT OR IGNORE INTO users (discord_id, nickname, anonymous) VALUES (?, ?, ?)''',
                       (ctx.author.id, ctx.author.display_name, True))

        # Record an attempt even if they've solved before
        cursor.execute('INSERT INTO attempts (user_id, potd_id, official, submission, submit_time) VALUES (?,?,?,?,?)',
                       (ctx.author.id, potd_id, False, answer, datetime.now()))

        # Get the number of both official and unofficial attempts
        cursor.execute('SELECT COUNT(1) from attempts WHERE user_id = ? and potd_id = ? and official = ?',
                       (ctx.author.id, potd_id, True))
        official_attempts = cursor.fetchall()[0][0]
        cursor.execute('SELECT COUNT(1) from attempts WHERE user_id = ? and potd_id = ? and official = ?',
                       (ctx.author.id, potd_id, False))
        unofficial_attempts = cursor.fetchall()[0][0]

        if answer_is_correct:
            if not solved_before:
                # Record that they solved it.
                cursor.execute('INSERT INTO solves (user, problem_id, num_attempts, official) VALUES (?, ?, ?, ?)',
                               (ctx.author.id, potd_id, official_attempts + unofficial_attempts, False))
                await ctx.send(
                    f'Nice job! You solved {self.bot.config["otd_prefix"]}OTD `{potd_id}` after `{official_attempts + unofficial_attempts}` '
                    f'attempts (`{official_attempts}` official and `{unofficial_attempts}` unofficial). ')
            else:
                # Don't need to record that they solved it.
                await ctx.send(f'Nice job! However you solved this {self.bot.config["otd_prefix"]}OTD already. ')

            # Log this stuff
            self.logger.info(f'[Unofficial] User {ctx.author.id} solved {self.bot.config["otd_prefix"]}OTD {potd_id}')
        else:
            await ctx.send(f"Sorry! That's the wrong answer. You've had `{official_attempts + unofficial_attempts}` "
                           f"attempts (`{official_attempts}` official and `{unofficial_attempts}` unofficial). ")

            # Log this stuff
            self.logger.info(
                f'[Unofficial] User {ctx.author.id} submitted wrong answer {answer} for '
                f'{self.bot.config["otd_prefix"]}OTD {potd_id}. ')

        # Delete the message if it's in a guild
        if ctx.guild is not None:
            await ctx.message.delete()

        # Still should refresh the embed
        await self.update_embed(potd_id)

        self.bot.db.commit()

    @commands.command(brief='Some information about the bot. ')
    async def info(self, ctx):
        embed = discord.Embed(description='OpenPOTD is a bot that posts short answer questions once a day for you '
                                          'to solve. OpenPOTD is open-source, and you can find our GitHub repository '
                                          'at https://github.com/IcosahedralDice/OpenPOTD. \n'
                                          'Have a bug report? Want to propose some problems? Join the OpenPOTD '
                                          'development server at https://discord.gg/ub2Y8b8zpt. \n'
                                          'Get the OpenPOTD manual with the `manual` command. ')
        await ctx.send(embed=embed)

    @commands.command(brief='Download the OpenPOTD manual. ')
    async def manual(self, ctx):
        await ctx.send('OpenPOTD Manual: ', file=discord.File('openpotd-manual.pdf'))


def setup(bot: openpotd.OpenPOTD):
    bot.add_cog(Interface(bot))
