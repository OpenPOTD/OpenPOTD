import logging
from datetime import datetime

import discord
from discord.ext import commands

import openpotd


# Change this if you want a different algorithm
def weighted_score(attempts: int):
    return 0.9 ** (attempts - 1)


class Interface(commands.Cog):
    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot
        self.logger = logging.getLogger('interface')

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

    def update_rankings(self, season: int):
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
        self.logger.info(f'Total scores: {str(total_score)}')

        # Prepare data to be put into the db
        total_score_list = [(i, total_score[i]) for i in total_score]
        total_score_list.sort(key=lambda x: -x[1])
        cursor.executemany('update rankings SET rank = ?, score = ? WHERE user_id = ? and season_id = ?',
                           [(i + 1, total_score_list[i][1], total_score_list[i][0], season) for i in
                            range(len(total_score_list))])

        # Commit
        self.bot.db.commit()

    def refresh(self, season: int):
        self.update_rankings(season)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is not None or message.author.id == self.bot.user.id \
                or message.content[0] == self.bot.config['prefix']:  # you can't submit answers in a server
            return

        # Validating int-ness
        s = message.content
        if not (s[1:].isdecimal() if s[0] in ('-', '+') else s.isdecimal()):
            await message.channel.send('Please provide an integer answer! ')
            return
        else:
            answer = int(s)

        # Get the current answer from the database
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT answer, problems.id, seasons.id from seasons left join problems '
                       'where seasons.running = ? and problems.id = seasons.latest_potd', (True,))
        correct_answer_list = cursor.fetchall()

        # Make sure the user is registered
        cursor.execute('INSERT or IGNORE into users (discord_id) VALUES (?)', (message.author.id,))
        self.bot.db.commit()

        if len(correct_answer_list) == 0:
            await message.channel.send('There is no current POTD to check answers against. ')
            return
        else:
            correct_answer, potd_id, season_id = correct_answer_list[0][0], correct_answer_list[0][1], \
                                                 correct_answer_list[0][2]

            # Put a ranking entry in for them
            cursor.execute('INSERT or IGNORE into rankings (season_id, user_id) VALUES (?, ?)',
                           (season_id, message.author.id,))
            self.bot.db.commit()

            # Check that they have not already solved this problem
            cursor.execute('SELECT exists (select 1 from solves where problem_id = ? and solves.user = ?)',
                           (potd_id, message.author.id))
            if cursor.fetchall()[0][0]:
                await message.channel.send('You have already solved this potd! ')
                return

            # We got to record the submission anyway even if it is right or wrong
            cursor.execute('INSERT into attempts (user_id, potd_id, official, submission, submit_time) '
                           'VALUES (?, ?, ?, ?, ?)',
                           (message.author.id, potd_id, True, int(message.content), datetime.utcnow()))
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
                self.refresh(season_id)

                # Alert user that they got the question correct
                await message.channel.send(f'Thank you! You solved the problem after {num_attempts} attempts. ')

                # Give them the "solved" role
                role_id = self.bot.config['solved_role_id']
                if role_id is not None:
                    self.logger.warning('Config variable solved_role_id is not set!')
                    for guild in self.bot.guilds:
                        if guild.get_role(role_id) is not None:
                            member = guild.get_member(message.author.id)
                            if member is not None:
                                await member.add_roles(guild.get_role(role_id), reason='Solved potd')
                            else:
                                self.logger.warning(f'User {message.author.id} solved the POTD despite not being '
                                                    f'in the server. ')
                            break
                    else:
                        self.logger.error('No guild found with a role matching the id set in solved_role_id!')

                # Logged that they solved it
                self.logger.info(f'User {message.author.id} just solved potd {potd_id}. ')

            else:
                # They got it wrong
                await message.channel.send(f'You did not solve this problem! Number of attempts: `{num_attempts}`. ')

                # Recalculate stuff anyway
                self.refresh(season_id)

                # Log that they didn't solve it
                self.logger.info(f'User {message.author.id} submitted incorrect answer {answer} for potd {potd_id}. ')

    @commands.command()
    async def score(self, ctx, season: int = None):
        cursor = self.bot.db.cursor()
        szn_name = None
        if season is None:
            cursor.execute('SELECT id, name from seasons where running = ?', (True,))
            running_seasons = cursor.fetchall()
            if len(running_seasons) == 0:
                await ctx.send('No current running season. Please specify a season. ')
                return
            else:
                season = running_seasons[0][0]
                szn_name = running_seasons[0][1]

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
        szn_name = None
        if season is None:
            cursor.execute('SELECT id, name from seasons where running = ?', (True,))
            running_seasons = cursor.fetchall()
            if len(running_seasons) == 0:
                await ctx.send('No current running season. Please specify a season. ')
                return
            else:
                season = running_seasons[0][0]
                szn_name = running_seasons[0][1]

        cursor.execute('SELECT rank, score, user_id from rankings where season_id = ? order by rank', (season,))
        rankings = cursor.fetchall()
        embed = discord.Embed(title=f'Current rankings for {szn_name}',
                              description='\n'.join((f'{rank[0]}. {rank[1]:.2f} [<@!{rank[2]}>]' for rank in rankings)))
        await ctx.send(embed=embed)


def setup(bot: openpotd.OpenPOTD):
    bot.add_cog(Interface(bot))
