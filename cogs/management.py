import io
import re
import sqlite3
from datetime import date
from datetime import datetime
from typing import Optional

import logging

import discord
import schedule
from discord import app_commands
from discord.ext import commands

import openpotd
import shared

authorised_set = set()


def authorised(interaction: discord.Interaction) -> bool:
    return interaction.user.id in authorised_set


class Management(commands.Cog):

    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot
        self.logger = logging.getLogger('management')
        schedule.every().day.at(self.bot.config['posting_time']).do(self.schedule_potd)
        global authorised_set
        authorised_set = set(self.bot.config['authorised'] or [])

        # Replicate the old global blacklist check: no command may run for a
        # blacklisted user.
        for command in self.__cog_app_commands__:
            command.add_check(shared.not_blacklisted)

    def schedule_potd(self):
        self.bot.loop.create_task(self.advance_potd())

    async def advance_potd(self):
        # Let the bot and users know we are posting the problem
        await self.bot.started_posting()

        self.logger.info(f'Advancing POTD at {datetime.now()}')
        cursor = self.bot.db.cursor()

        cursor.execute('SELECT server_id, potd_channel, ping_role_id, solved_role_id, otd_prefix from config '
                       'WHERE potd_channel IS NOT NULL')
        servers = cursor.fetchall()

        cursor.execute('SELECT problems.id, difficulty from (seasons inner join problems on seasons.running = ? '
                       'and seasons.id = problems.season and problems.date = ? ) where problems.id IS NOT NULL',
                       (True, str(date.today())))
        result = cursor.fetchall()

        cursor.execute('SELECT EXISTS (SELECT * from seasons where seasons.running = ?)', (True,))
        running_seasons_exists = cursor.fetchall()[0][0]

        # If there's no running season at all then it isn't really "running late" more like just
        # not even having a season
        if not running_seasons_exists:
            # We just do nothing since we would have already announced the
            # fact that no seasons are running. 
            return

        # If there's a running season but no problem then say
        if len(result) == 0 or result[0][0] is None:
            for server in servers:
                potd_channel = self.bot.get_channel(server[1])
                if potd_channel is not None:
                    self.bot.loop.create_task(potd_channel.send(f'Sorry! We are running late on the {server[4].lower()}'
                                                                f'otd today. '))
                    self.logger.info(f'Informed server {server[0]} that there is no problem today.')
            return

        # Grab the potd
        potd_id = result[0][0]
        problem = shared.POTD(result[0][0], self.bot.db)

        # The solved role is held by the people the bot gave it to, i.e. the
        # solvers of the problem that has just finished. Without the members
        # intent the database is the only way to enumerate them.
        cursor.execute('SELECT latest_potd from seasons where running = ? and latest_potd is not null', (True,))
        previous_potds = [x[0] for x in cursor.fetchall()]

        for server in servers:
            # Post the problem
            try:
                await problem.post(self.bot, server[1], server[2])
            except Exception:
                self.logger.warning(f'Server {server[0]} channel doesn\'t exist.')

            # Remove the solved role from everyone who has it
            role_id = server[3]
            if role_id is not None:
                try:
                    guild = self.bot.get_guild(server[0])
                    if guild.get_role(role_id) is not None:
                        for previous_potd_id in previous_potds:
                            cursor.execute('SELECT user from solves where problem_id = ?', (previous_potd_id,))
                            for user_id in [x[0] for x in cursor.fetchall()]:
                                if user_id not in authorised_set:
                                    try:
                                        await self.bot.http.remove_role(server[0], user_id, role_id)
                                    except discord.NotFound:
                                        # The user is no longer in the guild
                                        continue
                                    except discord.Forbidden:
                                        self.logger.warning(f'Server {server[0]}: missing permissions to remove '
                                                            f'role {role_id} from {user_id}. ')
                except Exception as e:
                    self.logger.warning(f'Server {server[0]}, {e}')
            else:
                self.bot.logger.warning('Config variable solved_role_id is not set!')

        # Advance the season
        cursor.execute('SELECT season FROM problems WHERE id = ?', (potd_id,))
        season_id = cursor.fetchall()[0][0]
        cursor.execute('UPDATE seasons SET latest_potd = ? WHERE id = ?', (potd_id, season_id))

        # Make the new potd publicly available
        cursor.execute('UPDATE problems SET public = ? WHERE id = ?', (True, potd_id))

        # Clear cooldowns from the previous question
        self.bot.get_cog('Interface').cooldowns.clear()

        # Commit db
        self.bot.db.commit()

        # Log this
        self.logger.info(f'Posted {self.bot.config["otd_prefix"]}OTD {potd_id}. ')

        # Let the bot and users know we are done posting the problem
        await self.bot.finished_posting()

    @app_commands.command()
    @app_commands.check(authorised)
    async def post(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.advance_potd()
        await interaction.followup.send('Done!', ephemeral=True)

    @app_commands.command()
    @app_commands.check(authorised)
    async def newseason(self, interaction: discord.Interaction, name: str):
        cursor = self.bot.db.cursor()
        cursor.execute('''INSERT INTO seasons (running, name) VALUES (?, ?)''', (False, name))
        self.bot.db.commit()
        cursor.execute('''SELECT LAST_INSERT_ROWID()''')
        rowid = cursor.fetchone()[0]
        await interaction.response.send_message(f'Added a new season called `{name}` with id `{rowid}`. ')
        self.logger.info(f'{interaction.user.id} added a new season called {name} with id {rowid}. ')

    @app_commands.command()
    @app_commands.check(authorised)
    async def add(self, interaction: discord.Interaction, season: int, prob_date: str, answer: int, statement: str):
        try:
            prob_date_parsed = date.fromisoformat(prob_date)
        except ValueError:
            await interaction.response.send_message('Invalid date (specify yyyy-mm-dd)', ephemeral=True)
            return
        cursor = self.bot.db.cursor()
        cursor.execute('''INSERT INTO problems ("date", season, statement, answer, public) VALUES (?, ?, ?, ?, ?)''',
                       (prob_date_parsed, season, statement, answer, False))
        self.bot.db.commit()
        await interaction.response.send_message(f'Added problem. ID: `{cursor.lastrowid}`.')
        self.logger.info(f'{interaction.user.id} added a new problem. ')

    @app_commands.command()
    @app_commands.check(authorised)
    @app_commands.describe(image='The image to attach to the problem. ')
    async def linkimg(self, interaction: discord.Interaction, problem: shared.POTDArgument,
                      image: discord.Attachment):
        # Defer first: downloading the attachment can exceed the 3 second
        # window in which the initial interaction response must arrive.
        await interaction.response.defer(ephemeral=True)
        potd = problem.id
        save_path = io.BytesIO()
        await image.save(save_path)
        cursor = self.bot.db.cursor()
        cursor.execute('''INSERT INTO images (potd_id, image) VALUES (?, ?)''',
                       (potd, sqlite3.Binary(save_path.getbuffer())))
        self.bot.db.commit()
        save_path.close()
        await interaction.followup.send(f'Linked an image to {self.bot.config["otd_prefix"]}OTD {potd}. ',
                                        ephemeral=True)

    @app_commands.command(description='Note: this is the admin version of the command so all problems are visible. ')
    @app_commands.check(authorised)
    async def showpotd(self, interaction: discord.Interaction, problem: shared.POTDArgument):
        images = problem.images
        if len(images) == 0:
            await interaction.response.send_message(f'{self.bot.config["otd_prefix"]}OTD {problem.id} of '
                                                    f'{problem.date} has no picture attached. ')
        else:
            await interaction.response.send_message(f'{self.bot.config["otd_prefix"]}OTD {problem.id} of {problem.date}',
                                                    file=discord.File(io.BytesIO(images[0]),
                                                                      filename=f'POTD-{problem.id}-0.png'))
            for i in range(1, len(images)):
                await interaction.followup.send(file=discord.File(io.BytesIO(images[i]),
                                                                  filename=f'POTD-{problem.id}-{i}.png'))

    @app_commands.command()
    @app_commands.check(authorised)
    async def update(self, interaction: discord.Interaction, problem: shared.POTDArgument,
                     date: Optional[str] = None, season: Optional[int] = None, statement: Optional[str] = None,
                     difficulty: Optional[int] = None, answer: Optional[int] = None, public: Optional[bool] = None,
                     source: Optional[str] = None):
        potd = problem.id
        cursor = self.bot.db.cursor()
        if not date is None and not bool(re.match(r'\d\d\d\d-\d\d-\d\d', date)):
            await interaction.response.send_message('Invalid date (specify yyyy-mm-dd)', ephemeral=True)
            return

        params = {'date': date, 'season': season, 'statement': statement, 'difficulty': difficulty,
                  'answer': answer, 'public': public, 'source': source}
        for param in params:
            if params[param] is not None:
                cursor.execute(f'UPDATE problems SET {param} = ? WHERE id = ?', (params[param], potd))
        self.bot.db.commit()
        await interaction.response.send_message(f'Updated {self.bot.config["otd_prefix"].lower()}otd. ')

    @app_commands.command(name='pinfo')
    @app_commands.check(authorised)
    async def info(self, interaction: discord.Interaction, problem: shared.POTDArgument):
        info = problem.info()
        embed = discord.Embed(title=f'{self.bot.config["otd_prefix"]}OTD {problem.id}')
        for i in range(len(info)):
            embed.add_field(name=info[i][0], value=f'`{info[i][1]}`', inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command()
    @app_commands.check(authorised)
    async def start_season(self, interaction: discord.Interaction, season: int):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT running from seasons where seasons.id = ?', (season,))
        result = cursor.fetchall()

        if len(result) == 0:
            await interaction.response.send_message(f'No season with id {season}.', ephemeral=True)
            return

        running = result[0][0]
        if not running:
            cursor.execute('UPDATE seasons SET running = ? where seasons.id = ?', (True, season))
            self.bot.db.commit()
            self.logger.info(f'Started season with id {season}. ')
            await interaction.response.send_message(f'Started season with id {season}. ', ephemeral=True)
        else:
            await interaction.response.send_message(f'Season {season} already running!', ephemeral=True)

    @app_commands.command()
    @app_commands.check(authorised)
    async def end_season(self, interaction: discord.Interaction, season: int):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT running from seasons where seasons.id = ?', (season,))
        result = cursor.fetchall()

        if len(result) == 0:
            await interaction.response.send_message(f'No season with id {season}.', ephemeral=True)
            return

        running = result[0][0]
        if running:
            cursor.execute('UPDATE seasons SET running = ? where seasons.id = ?', (False, season))
            self.bot.db.commit()
            self.logger.info(f'Ended season with id {season}. ')
            await interaction.response.send_message(f'Ended season with id {season}. ', ephemeral=True)
        else:
            await interaction.response.send_message(f'Season {season} already stopped!', ephemeral=True)

    @app_commands.command()
    @app_commands.check(shared.is_owner)
    async def execute_sql(self, interaction: discord.Interaction, sql: str):
        cursor = self.bot.db.cursor()
        try:
            cursor.execute(sql)
        except Exception as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await interaction.response.send_message(str(cursor.fetchall()), ephemeral=True)

    @app_commands.command()
    @app_commands.check(shared.is_owner)
    async def init_nicks(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT discord_id from users where nickname is NULL')
        users_to_check = [x[0] for x in cursor.fetchall()]

        to_update = []
        for user_id in users_to_check:
            try:
                user: discord.User = await self.bot.fetch_user(user_id)
                to_update.append((user.display_name, user_id))
            except discord.NotFound:
                to_update.append(('Unknown', user_id))

        cursor.executemany('UPDATE users SET nickname = ? where discord_id = ?', to_update)
        self.bot.db.commit()
        await interaction.followup.send('Done!', ephemeral=True)

    @app_commands.command()
    @app_commands.check(authorised)
    async def announce(self, interaction: discord.Interaction, message: str):
        # Defer first: the channel sends below can exceed the 3 second window
        # in which the initial interaction response must arrive.
        await interaction.response.defer(ephemeral=True)
        message = discord.utils.escape_mentions(message)
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT potd_channel from config where potd_channel is not null')
        potd_channels = [x[0] for x in cursor.fetchall()]
        self.logger.info(f"[ANNOUNCE] Announcement created by {interaction.user.id}")

        for channel_id in potd_channels:
            channel: discord.TextChannel = self.bot.get_channel(channel_id)
            if channel is not None:
                try:
                    await channel.send(message)
                except Exception as e:
                    self.logger.warning(f"[ANNOUNCE] Can't send messages in {channel_id}")

        await interaction.followup.send('Announced!', ephemeral=True)

    @app_commands.command()
    @app_commands.check(authorised)
    async def set_cutoffs(self, interaction: discord.Interaction, season: int, bronze: int, silver: int, gold: int):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT EXISTS (select 1 from seasons where id = ?)', (season,))
        season_exists = cursor.fetchall()[0][0]
        if season_exists:
            cursor.execute('UPDATE seasons SET bronze_cutoff = ?, silver_cutoff = ?, gold_cutoff = ? WHERE id = ?',
                           (bronze, silver, gold, season))
            self.bot.db.commit()
            await interaction.response.send_message('Done!')
        else:
            await interaction.response.send_message('No season with that ID!', ephemeral=True)

    @app_commands.command()
    @app_commands.check(authorised)
    async def assign_roles(self, interaction: discord.Interaction, season: int):
        await interaction.response.defer(ephemeral=True)
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT bronze_cutoff, silver_cutoff, gold_cutoff from seasons WHERE id = ?', (season,))
        result = cursor.fetchall()

        if len(result) == 0:
            await interaction.followup.send('No such season!', ephemeral=True)
            return

        cutoffs = result[0]
        cursor.execute('SELECT server_id, bronze_role_id, silver_role_id, gold_role_id from config')
        servers = cursor.fetchall()

        cursor.execute('SELECT user_id from rankings inner join users on rankings.user_id = users.discord_id '
                       'where season_id = ? and score > ? and score < ? and users.receiving_medal_roles = ?',
                       (season, cutoffs[0], cutoffs[1], True))
        bronzes = [x[0] for x in cursor.fetchall()]

        cursor.execute('SELECT user_id from rankings inner join users on rankings.user_id = users.discord_id '
                       'where season_id = ? and score > ? and score < ? and users.receiving_medal_roles = ?',
                       (season, cutoffs[1], cutoffs[2], True))
        silvers = [x[0] for x in cursor.fetchall()]

        cursor.execute('SELECT user_id from rankings inner join users on rankings.user_id = users.discord_id '
                       'where season_id = ? and score > ? and users.receiving_medal_roles = ?',
                       (season, cutoffs[2], True))
        golds = [x[0] for x in cursor.fetchall()]
        medallers = [bronzes, silvers, golds]

        # Medal roles are only ever given out by this command, so everyone who
        # could hold one is recorded in the rankings (any season, since the
        # same roles are reused). Without the members intent this is the only
        # way to enumerate the holders.
        cursor.execute('SELECT DISTINCT user_id from rankings')
        ranked_users = [x[0] for x in cursor.fetchall()]

        for server in servers:
            server_id = server[0]
            guild: discord.Guild = self.bot.get_guild(server_id)

            if guild is None:
                self.logger.warning(f'[{server_id}] Trying to assign roles: No such guild {server_id}')
                continue

            try:
                self_member: discord.Member = await guild.fetch_member(self.bot.user.id)
            except discord.NotFound:
                self.logger.warning(f'[{server_id}] Trying to assign roles: Not a member of guild {server_id}')
                continue
            if not discord.Permissions.manage_roles.flag & self_member.guild_permissions.value:
                self.logger.warning(f'[{server_id}] Trying to assign roles: No permissions in guild {server_id}')
                continue

            # Clear all the bronze, silver and gold roles
            for x in (server[1], server[2], server[3]):  # Bronze, Silver, Gold role IDs
                if x is not None:
                    medal_role: discord.Role = guild.get_role(x)
                    if medal_role is None:
                        self.logger.warning(f'[{server_id}] Trying to assign roles: Guild {server_id} has no role {x}')
                        continue
                    for user_id in ranked_users:
                        try:
                            await self.bot.http.remove_role(server_id, user_id, x)
                        except discord.NotFound:
                            # The user is no longer in the guild
                            continue
                        except Exception as e:
                            self.logger.warning(f'[{server_id}] Trying to assign roles: '
                                                f'Guild {server_id} missing permissions. ')

            self.logger.info(f'[{server_id}] Removed all medal roles from guild {server_id}')

            # Give roles
            for x in range(3):
                if server[x + 1] is not None:
                    medal_role: discord.Role = guild.get_role(server[x + 1])
                    if medal_role is None:
                        self.logger.warning(f'[{server_id}] No role {server[x + 1]} ({x})')
                        continue
                    for user_id in medallers[x]:
                        try:
                            await self.bot.http.add_role(server_id, user_id, server[x + 1])
                        except discord.NotFound:
                            # The user is no longer in the guild
                            continue
                        except Exception as e:
                            self.logger.warning(f'[{server_id}] Trying to assign roles: '
                                                f'Guild {server_id} missing permissions. [{user_id}]')
                            continue
                        self.logger.info(f'[{server_id}] Gave {user_id} role {medal_role.name}')

        await interaction.followup.send('Done!', ephemeral=True)

    @app_commands.command()
    @app_commands.check(authorised)
    async def clear_imgs(self, interaction: discord.Interaction, problem: shared.POTDArgument):
        cursor = self.bot.db.cursor()
        cursor.execute('DELETE FROM images WHERE potd_id = ?', (problem.id,))
        self.bot.db.commit()

        await interaction.response.send_message('Cleared images!')

    @app_commands.command()
    @app_commands.check(authorised)
    async def force_update(self, interaction: discord.Interaction, season: int):
        await interaction.response.defer(ephemeral=True)
        try:
            self.bot.get_cog('Interface').update_rankings(season)
        except Exception as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        await interaction.followup.send('Done!', ephemeral=True)

    @app_commands.command()
    @app_commands.check(authorised)
    async def change_answer(self, interaction: discord.Interaction, problem: shared.POTDArgument, new_answer: int):
        await interaction.response.defer(ephemeral=True)
        # Get all attempts and current solves
        cursor = self.bot.db.cursor()

        cursor.execute(
            'SELECT user_id, submission from attempts where potd_id = ? and official = ? order by submit_time',
            (problem.id, True))
        attempts = cursor.fetchall()

        # Put attempts into a dictionary instead of a list
        attempts_dict = {}
        for attempt in attempts:
            if attempt[0] in attempts_dict:
                attempts_dict[attempt[0]].append(attempt[1])
            else:
                attempts_dict[attempt[0]] = [attempt[1]]

        cursor.execute('SELECT user, num_attempts from solves where problem_id = ? and official = ?',
                       (problem.id, True))
        solves = cursor.fetchall()
        # Same with solves
        solves_dict = {}
        for solve in solves:
            if solve[0] in solves_dict:
                solves_dict[solve[0]].append(solve[1])
            else:
                solves_dict[solve[0]] = [solve[1]]

        # See who actually solved it (with new answer)
        new_solves = {}
        for user in attempts_dict:
            if new_answer in attempts_dict[user]:
                # Find the place where they first submitted the right answer
                new_solves[user] = attempts_dict[user].index(new_answer) + 1

        # Make sets
        new_solved_set = set((i for i in new_solves))
        old_solved_set = set((i for i in solves_dict))

        submitted_new_only = new_solved_set - old_solved_set
        submitted_both_ans = new_solved_set.intersection(old_solved_set)
        submitted_old_only = old_solved_set - new_solved_set

        # DM people whom the change relates to
        for user in submitted_new_only:
            try:
                user_obj = await self.bot.fetch_user(user)
                await user_obj.send(f'The answer {new_answer} that you submitted on attempt '
                                    f'{new_solves[user]} is actually correct. ')
                self.logger.info(
                    f'[CHANGE ANS] [SUBMITTED NEW ONLY] User {user} solved after {new_solves[user]} attempts')
            except Exception as e:
                self.logger.warning(f'[CHANGE ANS] [SUBMITTED NEW ONLY] User {user} Exception when DMing {e}')

        for user in submitted_both_ans:
            try:
                user_obj = await self.bot.fetch_user(user)
                await user_obj.send(
                    f'The answer has changed; the answer {new_answer} that you submitted on attempt '
                    f'{new_solves[user]} is actually correct. ')
                self.logger.info(
                    f'[CHANGE ANS] [SUBMITTED BOTH ANS] User {user} solved after {new_solves[user]} attempts')
            except Exception as e:
                self.logger.warning(f'[CHANGE ANS] [SUBMITTED BOTH ANS] User {user} Exception when DMing {e}')

        for user in submitted_old_only:
            try:
                user_obj = await self.bot.fetch_user(user)
                await user_obj.send(
                    f'The answer has changed; the previous answers you submitted are now incorrect. ')
                self.logger.info(f'[CHANGE ANS] [SUBMITTED OLD ONLY] User {user} no longer solves the problem')
            except Exception as e:
                self.logger.warning(f'[CHANGE ANS] [SUBMITTED OLD ONLY] User {user} Exception when DMing {e}')

        # Sort out roles - give to those in new_ans and take from those in old_ans
        cursor.execute('SELECT server_id, solved_role_id from config where solved_role_id is not null')
        servers = cursor.fetchall()

        for user in submitted_new_only:
            await shared.assign_solved_role(servers, user, True, self.bot)
        for user in submitted_old_only:
            await shared.assign_solved_role(servers, user, False, self.bot)

        # Update DB rankings
        # Remove all solves
        cursor.execute('DELETE FROM solves where problem_id = ?', (problem.id,))
        self.bot.db.commit()

        # Add the new rankings
        cursor.executemany('INSERT INTO solves (user, problem_id, num_attempts, official) VALUES (?, ?, ?, ?)',
                           [
                               (user, problem.id, new_solves[user], True)
                               for user in new_solves])
        self.bot.db.commit()

        # Change the answer
        cursor.execute('UPDATE problems SET answer = ? WHERE id = ?', (new_answer, problem.id))
        self.bot.db.commit()

        # Update rankings
        self.bot.get_cog('Interface').update_rankings(problem.season)

        await interaction.followup.send('Done!', ephemeral=True)


async def setup(bot: openpotd.OpenPOTD):
    await bot.add_cog(Management(bot))
