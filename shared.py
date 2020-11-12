"""A bunch of helper functions. """
import re
import sqlite3
from datetime import date

import discord
from discord.ext import commands
import logging
import io
import openpotd

date_regex = re.compile('\d\d\d\d-\d\d-\d\d')


def id_from_date_or_id(date_or_id: str, conn: sqlite3.Connection, is_public: bool = True):
    if bool(date_regex.match(date_or_id)):  # Then the user passed in a date
        cursor = conn.cursor()
        if is_public:
            cursor.execute('SELECT id, statement from problems where date = ? and public = ?', (date_or_id, True))
        else:
            cursor.execute('SELECT id, statement from problems where date = ?', (date_or_id,))

        result = cursor.fetchall()
        if len(result) == 0:
            raise Exception(f'There are no problems available for the date {date_or_id}. ')
        elif len(result) == 2:
            space = ' '

            # Get the id and first 10 letters of each problem.
            problems = ', '.join((f'{x[0]}: "{space.join(x[1].split(space)[:10])}..."' for x in result))
            raise Exception(f'There are multiple problems available for the date {date_or_id}: {problems}. ')
        else:
            # Return the unique ID.
            return result[0][0]
    elif date_or_id.isdecimal():
        potd_id = int(date_or_id)
        cursor = conn.cursor()
        if is_public:
            cursor.execute('SELECT EXISTS (SELECT id from problems where problems.id = ? and public = ? limit 1)',
                           (potd_id, True))
        else:
            cursor.execute('SELECT EXISTS (SELECT id from problems where problems.id = ? limit 1)', (potd_id,))
        if cursor.fetchall()[0][0]:
            return potd_id
        else:
            raise Exception(f'There are no problems available for the id {date_or_id}. ')
    else:
        raise Exception(f'Please enter a valid id or date. ')


class POTD:
    """Representation of a problem of the day. """

    def __init__(self, id: int, db: sqlite3.Connection):
        cursor = db.cursor()
        cursor.execute('SELECT * from problems WHERE id = ?', (id,))
        result = cursor.fetchall()
        if len(result) == 0:
            raise Exception('No such problem! ')
        else:
            self.id = id
            self.date = result[0][1]
            self.season = result[0][2]
            self.statement = result[0][3]
            self.difficulty = result[0][4]
            self.weighted_solves = result[0][5]
            self.base_points = result[0][6]
            self.answer = result[0][7]
            self.public = result[0][8]
            self.source = result[0][9]
            self.stats_message_id = result[0][10]
            cursor.execute('SELECT image from images WHERE potd_id = ?', (id,))
            self.images = [x[0] for x in cursor.fetchall()]
            self.logger = logging.getLogger(f'POTD {self.id}')
            self.db = db

    async def post(self, bot: openpotd.OpenPOTD, channel: int, potd_role_id: int):
        channel = bot.get_channel(channel)
        if channel is None:
            raise Exception('No such channel!')
        else:
            try:
                if len(self.images) == 0:
                    await channel.send(
                        f'{bot.config["otd_prefix"]}OTD {self.id} of {str(date.today())} has no picture attached. ')
                else:
                    await channel.send(f'{bot.config["otd_prefix"]}OTD {self.id} of {str(date.today())}',
                                       file=discord.File(io.BytesIO(self.images[0]),
                                                         filename=f'POTD-{self.id}-0.png'))
                    for i in range(1, len(self.images)):
                        await channel.send(
                            file=discord.File(io.BytesIO(self.images[i]), filename=f'POTD-{self.id}-{i}.png'))

                if potd_role_id is not None:
                    await channel.send(f'DM your answers to me! <@&{potd_role_id}>')
                else:
                    await channel.send(f'DM your answers to me!')
                    logging.warning(f'Config variable ping_role_id is not set! [Server {channel.guild.id}]')

                # Construct embed and send
                embed = discord.Embed(title=f'{bot.config["otd_prefix"]}oTD {self.id} Stats')
                embed.add_field(name='Difficulty', value=self.difficulty)
                embed.add_field(name='Weighted Solves', value='0')
                embed.add_field(name='Base Points', value='0')
                embed.add_field(name='Solves (official)', value='0')
                embed.add_field(name='Solves (unofficial)', value='0')
                stats_message = await channel.send(embed=embed)
                self.add_stats_message(stats_message.id)
            except Exception as e:
                self.logger.warning(e)

    def add_stats_message(self, message_id: int):
        cursor = self.db.cursor()
        cursor.execute('INSERT INTO stats_messages (potd_id, message_id) VALUES (?, ?)', (self.id, message_id))
        self.db.commit()
