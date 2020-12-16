import io
import re
import sqlite3
from datetime import date
from datetime import datetime
import logging

import discord
import schedule
from discord.ext import commands
from discord.ext import flags

import openpotd
import shared

authorised_set = set()


def authorised(ctx):
    return ctx.author.id in authorised_set


class Management(commands.Cog):

    def __init__(self, bot: openpotd.OpenPOTD):
        self.bot = bot
        self.logger = logging.getLogger('management')
        schedule.every().day.at(self.bot.config['posting_time']).do(self.schedule_potd)
        global authorised_set
        authorised_set = self.bot.config['authorised']

    def schedule_potd(self):
        self.bot.loop.create_task(self.advance_potd())

    async def advance_potd(self):
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
            for server in servers:
                potd_channel = self.bot.get_channel(server[1])
                if potd_channel is not None:
                    self.bot.loop.create_task(potd_channel.send(f'There is no season in session today. '))
                    self.logger.info(f'Informed server {server[0]} that there is no season today.')
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

        for server in servers:
            # Post the problem
            try:
                await problem.post(self.bot, server[1], server[2])
            except Exception:
                self.logger.warning(f'Server {server[0]} channel doesn\'t exist.')

            # Remove the solved role from everyone
            role_id = server[3]
            if role_id is not None:
                try:
                    self.bot.logger.warning('Config variable solved_role_id is not set!')
                    guild = self.bot.get_guild(server[0])
                    if guild.get_role(role_id) is not None:
                        role = guild.get_role(role_id)
                        for member in role.members:
                            if member.id not in authorised_set:
                                await member.remove_roles(role)
                except Exception as e:
                    self.logger.warning(f'Server {server[0]}, {e}')

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

    @commands.command()
    @commands.check(authorised)
    async def post(self, ctx):
        await self.advance_potd()

    @commands.command()
    @commands.check(authorised)
    async def newseason(self, ctx, *, name):
        cursor = self.bot.db.cursor()
        cursor.execute('''INSERT INTO seasons (running, name) VALUES (?, ?)''', (False, name))
        self.bot.db.commit()
        cursor.execute('''SELECT LAST_INSERT_ROWID()''')
        rowid = cursor.fetchone()[0]
        await ctx.send(f'Added a new season called `{name}` with id `{rowid}`. ')
        self.logger.info(f'{ctx.author.id} added a new season called {name} with id {rowid}. ')

    @commands.command()
    @commands.check(authorised)
    async def add(self, ctx, season: int, prob_date, answer, *, statement):
        cursor = self.bot.db.cursor()
        prob_date_parsed = date.fromisoformat(prob_date)
        cursor.execute('''INSERT INTO problems ("date", season, statement, answer, public) VALUES (?, ?, ?, ?, ?)''',
                       (prob_date_parsed, season, statement, answer, False))
        self.bot.db.commit()
        await ctx.send(f'Added problem. ID: `{cursor.lastrowid}`.')
        self.logger.info(f'{ctx.author.id} added a new problem. ')

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
                await ctx.send(f'No such {self.bot.config["otd_prefix"].lower()}otd. ')
                return

        else:  # User passed in a date
            potd_date = potd
            cursor.execute('''SELECT id from problems WHERE date = ?''', (potd_date,))
            result = cursor.fetchall()
            if len(result) == 0:
                await ctx.send(f'No such {self.bot.config["otd_prefix"]}OTD found. ')
                return
            else:
                potd_id = result[0][0]

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

    @flags.add_flag('--date')
    @flags.add_flag('--season', type=int)
    @flags.add_flag('--statement')
    @flags.add_flag('--difficulty', type=int)
    @flags.add_flag('--answer', type=int)
    @flags.add_flag('--public', type=bool)
    @flags.add_flag('--source')
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
        await ctx.send(f'Updated {self.bot.config["otd_prefix"].lower()}otd. ')

    @commands.command(name='pinfo')
    @commands.check(authorised)
    async def info(self, ctx, potd):
        cursor = self.bot.db.cursor()
        if potd.isdecimal():
            cursor.execute('SELECT * FROM problems WHERE id = ?', (int(potd),))
        else:
            cursor.execute('SELECT * FROM problems WHERE date = ?', (potd,))

        result = cursor.fetchall()
        if len(result) == 0:
            await ctx.send(f'No such {self.bot.config["otd_prefix"].lower()}otd. ')
            return

        columns = ['id', 'date', 'season', 'statement',
                   'difficulty', 'weighted_solves', 'base_points', 'answer', 'public', 'source']
        embed = discord.Embed(title=f'{self.bot.config["otd_prefix"]}OTD {result[0][0]}')
        for i in range(len(columns)):
            embed.add_field(name=columns[i], value=f'`{result[0][i]}`', inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.check(authorised)
    async def start_season(self, ctx, season: int):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT running from seasons where seasons.id = ?', (season,))
        result = cursor.fetchall()

        if len(result) == 0:
            await ctx.send(f'No season with id {season}.')
            return

        running = result[0][0]
        if not running:
            cursor.execute('UPDATE seasons SET running = ? where seasons.id = ?', (True, season))
            self.bot.db.commit()
            self.logger.info(f'Started season with id {season}. ')
        else:
            await ctx.send(f'Season {season} already running!')

    @commands.command()
    @commands.check(authorised)
    async def end_season(self, ctx, season: int):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT running from seasons where seasons.id = ?', (season,))
        result = cursor.fetchall()

        if len(result) == 0:
            await ctx.send(f'No season with id {season}.')
            return

        running = result[0][0]
        if running:
            cursor.execute('UPDATE seasons SET running = ? where seasons.id = ?', (False, season))
            self.bot.db.commit()
            self.logger.info(f'Ended season with id {season}. ')
        else:
            await ctx.send(f'Season {season} already stopped!')

    @commands.command()
    @commands.is_owner()
    async def execute_sql(self, ctx, *, sql):
        cursor = self.bot.db.cursor()
        try:
            cursor.execute(sql)
        except Exception as e:
            await ctx.send(e)
        await ctx.send(str(cursor.fetchall()))

    @commands.command()
    @commands.is_owner()
    async def init_nicks(self, ctx):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT discord_id from users where nickname is NULL')
        users_to_check = [x[0] for x in cursor.fetchall()]

        to_update = []
        for user_id in users_to_check:
            user: discord.User = self.bot.get_user(user_id)
            if user is not None:
                to_update.append((user.display_name, user_id))
            else:
                to_update.append(('Unknown', user_id))

        cursor.executemany('UPDATE users SET nickname = ? where discord_id = ?', to_update)
        self.bot.db.commit()
        await ctx.send('Done!')

    @commands.command()
    @commands.is_owner()
    async def announce(self, ctx, *, message):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT potd_channel from config where potd_channel is not null')
        potd_channels = [x[0] for x in cursor.fetchall()]

        for channel_id in potd_channels:
            channel: discord.TextChannel = self.bot.get_channel(channel_id)
            if channel is not None:
                await channel.send(message)

    @commands.command()
    @commands.check(authorised)
    async def set_cutoffs(self, ctx, season: int, bronze: int, silver: int, gold: int):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT EXISTS (select 1 from seasons where id = ?)', (season,))
        season_exists = cursor.fetchall()[0][0]
        if season_exists:
            cursor.execute('UPDATE seasons SET bronze_cutoff = ?, silver_cutoff = ?, gold_cutoff = ? WHERE id = ?',
                           (bronze, silver, gold, season))
            self.bot.db.commit()
            await ctx.send('Done!')
        else:
            await ctx.send('No season with that ID!')

    @commands.command()
    @commands.check(authorised)
    async def assign_roles(self, ctx, season: int):
        cursor = self.bot.db.cursor()
        cursor.execute('SELECT bronze_cutoff, silver_cutoff, gold_cutoff from seasons WHERE id = ?', (season,))
        result = cursor.fetchall()

        if len(result) == 0:
            await ctx.send('No such season!')
            return

        cutoffs = result[0]
        cursor.execute('SELECT server_id, bronze_role_id, silver_role_id, gold_role_id from config')
        servers = cursor.fetchall()

        cursor.execute('SELECT user_id from rankings where season_id = ? and score > ? and score < ?',
                       (season, cutoffs[0], cutoffs[1]))
        bronzes = [x[0] for x in cursor.fetchall()]

        cursor.execute('SELECT user_id from rankings where season_id = ? and score > ? and score < ?',
                       (season, cutoffs[1], cutoffs[2]))
        silvers = [x[0] for x in cursor.fetchall()]

        cursor.execute('SELECT user_id from rankings where season_id = ? and score > ?',
                       (season, cutoffs[2]))
        golds = [x[0] for x in cursor.fetchall()]
        medallers = [bronzes, silvers, golds]

        for server in servers:
            server_id = server[0]
            guild: discord.Guild = self.bot.get_guild(server_id)

            if guild is None:
                self.logger.warning(f'[{server_id}] Trying to assign roles: No such guild {server_id}')
                continue

            self_member: discord.Member = guild.get_member(self.bot.user.id)
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
                    for user in medal_role.members:
                        user: discord.Member
                        await user.remove_roles(medal_role)
            self.logger.info(f'[{server_id}] Removed all medal roles from guild {server_id}')

            # Give roles
            for x in range(3):
                if server[x + 1] is not None:
                    medal_role: discord.Role = guild.get_role(server[x + 1])
                    if medal_role is None:
                        self.logger.warning(f'[{server_id}] No role {medal_role} ({x})')
                        continue
                    for user_id in medallers[x]:
                        if guild.get_member(user_id) is not None:
                            member: discord.Member = guild.get_member(user_id)
                            await member.add_roles(medal_role)
                            self.logger.info(f'[{server_id}] Gave {user_id} role {medal_role.name}')

        await ctx.send('Done!')


def setup(bot: openpotd.OpenPOTD):
    bot.add_cog(Management(bot))
